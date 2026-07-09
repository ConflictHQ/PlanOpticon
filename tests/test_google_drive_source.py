"""Tests for the Google Drive source: listing, download, and auth branch dispatch.

The Google API Python client SDK is not installed in this environment, so the
Drive service client is replaced with a fluent MagicMock and the lazily-imported
``googleapiclient`` / ``google_auth_oauthlib`` modules are injected into
``sys.modules``. The ``google.oauth2`` / ``google.auth`` packages *are* installed
(via ``google-auth``), so those are patched at their real attributes instead.

Constructors, the not-authenticated guards, and the basic ``_is_service_account``
cases are already covered by ``tests/test_cloud_sources.py`` and are not repeated
here; this module covers the untested listing/download/auth-branch code paths.
"""

import json
import sys
import types
from unittest.mock import MagicMock, patch

from video_processor.sources.base import SourceFile
from video_processor.sources.google_drive import SCOPES, GoogleDriveSource


def _fake_discovery_module(build_obj):
    """Inject a fake ``googleapiclient.discovery`` exposing ``build``."""
    pkg = types.ModuleType("googleapiclient")
    disc = types.ModuleType("googleapiclient.discovery")
    disc.build = build_obj
    pkg.discovery = disc
    return {"googleapiclient": pkg, "googleapiclient.discovery": disc}


def _fake_oauthlib_module(flow_cls):
    """Inject a fake ``google_auth_oauthlib.flow`` exposing ``InstalledAppFlow``."""
    pkg = types.ModuleType("google_auth_oauthlib")
    flowmod = types.ModuleType("google_auth_oauthlib.flow")
    flowmod.InstalledAppFlow = flow_cls
    pkg.flow = flowmod
    return {"google_auth_oauthlib": pkg, "google_auth_oauthlib.flow": flowmod}


def _fake_http_module(media_factory):
    """Inject a fake ``googleapiclient.http`` exposing ``MediaIoBaseDownload``."""
    pkg = types.ModuleType("googleapiclient")
    httpmod = types.ModuleType("googleapiclient.http")
    httpmod.MediaIoBaseDownload = media_factory
    pkg.http = httpmod
    return {"googleapiclient": pkg, "googleapiclient.http": httpmod}


class TestGoogleDriveIsServiceAccount:
    """The exception branch of ``_is_service_account`` (bad/missing file)."""

    def test_missing_file_returns_false(self, tmp_path):
        source = GoogleDriveSource(credentials_path=str(tmp_path / "does_not_exist.json"))
        assert source._is_service_account() is False

    def test_malformed_json_returns_false(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{ this is not valid json")
        source = GoogleDriveSource(credentials_path=str(bad))
        assert source._is_service_account() is False


class TestGoogleDriveAuthenticateDispatch:
    """``authenticate`` routes to the right auth helper once the SDK imports resolve."""

    def test_dispatch_service_account_forced(self):
        source = GoogleDriveSource(use_service_account=True)
        build_obj = MagicMock()
        with patch.dict(sys.modules, _fake_discovery_module(build_obj)):
            with patch.object(source, "_auth_service_account", return_value=True) as helper:
                assert source.authenticate() is True
        helper.assert_called_once()
        # The build callable imported from googleapiclient is threaded through.
        assert helper.call_args.args[0] is build_obj

    def test_dispatch_autodetect_service_account(self, tmp_path):
        creds = tmp_path / "sa.json"
        creds.write_text(json.dumps({"type": "service_account"}))
        source = GoogleDriveSource(credentials_path=str(creds))  # use_service_account is None
        build_obj = MagicMock()
        with patch.dict(sys.modules, _fake_discovery_module(build_obj)):
            with patch.object(source, "_auth_service_account", return_value=True) as helper:
                assert source.authenticate() is True
        helper.assert_called_once()

    def test_dispatch_oauth(self):
        source = GoogleDriveSource(use_service_account=False)
        build_obj = MagicMock()
        with patch.dict(sys.modules, _fake_discovery_module(build_obj)):
            with patch.object(source, "_auth_oauth", return_value=True) as helper:
                assert source.authenticate() is True
        helper.assert_called_once()
        assert helper.call_args.args[0] is build_obj


class TestGoogleDriveAuthServiceAccount:
    def test_success_builds_service(self, tmp_path):
        creds_file = tmp_path / "sa.json"
        creds_file.write_text(json.dumps({"type": "service_account"}))
        source = GoogleDriveSource(credentials_path=str(creds_file))
        build_obj = MagicMock()
        fake_creds = MagicMock()
        with patch(
            "google.oauth2.service_account.Credentials.from_service_account_file",
            return_value=fake_creds,
        ) as from_file:
            assert source._auth_service_account(build_obj) is True
        from_file.assert_called_once_with(str(creds_file), scopes=SCOPES)
        build_obj.assert_called_once_with("drive", "v3", credentials=fake_creds)
        assert source.service is build_obj.return_value
        assert source._creds is fake_creds

    def test_no_credentials_path_returns_false(self):
        source = GoogleDriveSource()
        source.credentials_path = None  # override any env-var fallback
        assert source._auth_service_account(MagicMock()) is False

    def test_exception_returns_false(self, tmp_path):
        creds_file = tmp_path / "sa.json"
        creds_file.write_text("{}")
        source = GoogleDriveSource(credentials_path=str(creds_file))
        with patch(
            "google.oauth2.service_account.Credentials.from_service_account_file",
            side_effect=ValueError("bad service account key"),
        ):
            assert source._auth_service_account(MagicMock()) is False
        assert source.service is None


class TestGoogleDriveAuthOAuth:
    def test_import_error_returns_false(self):
        # google_auth_oauthlib is not installed → the top-level import raises.
        source = GoogleDriveSource()
        assert source._auth_oauth(MagicMock()) is False

    def test_new_flow_saves_token(self, tmp_path):
        creds_file = tmp_path / "client.json"
        creds_file.write_text(
            json.dumps({"installed": {"client_id": "cid", "client_secret": "sec"}})
        )
        token_file = tmp_path / "token.json"  # does not exist yet
        source = GoogleDriveSource(credentials_path=str(creds_file), token_path=token_file)
        build_obj = MagicMock()
        new_creds = MagicMock()
        new_creds.to_json.return_value = json.dumps({"token": "abc"})
        flow_inst = MagicMock()
        flow_inst.run_local_server.return_value = new_creds
        flow_cls = MagicMock()
        flow_cls.from_client_config.return_value = flow_inst
        with patch.dict(sys.modules, _fake_oauthlib_module(flow_cls)):
            assert source._auth_oauth(build_obj) is True
        # Token persisted to disk from the freshly minted credentials.
        assert json.loads(token_file.read_text()) == {"token": "abc"}
        # Client config was loaded from the provided secrets file.
        cfg = flow_cls.from_client_config.call_args.args[0]
        assert cfg["installed"]["client_id"] == "cid"
        build_obj.assert_called_once_with("drive", "v3", credentials=new_creds)
        assert source.service is build_obj.return_value

    def test_valid_saved_token_skips_flow(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"token": "existing"}))
        source = GoogleDriveSource(token_path=token_file)
        build_obj = MagicMock()
        good_creds = MagicMock()
        good_creds.valid = True
        good_creds.expired = False
        flow_cls = MagicMock()
        with patch.dict(sys.modules, _fake_oauthlib_module(flow_cls)):
            with patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                return_value=good_creds,
            ):
                assert source._auth_oauth(build_obj) is True
        flow_cls.from_client_config.assert_not_called()
        build_obj.assert_called_once_with("drive", "v3", credentials=good_creds)
        assert source._creds is good_creds
        # The existing token file is left untouched when no new flow runs.
        assert json.loads(token_file.read_text()) == {"token": "existing"}

    def test_expired_token_is_refreshed(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text("{}")
        source = GoogleDriveSource(token_path=token_file)
        build_obj = MagicMock()
        creds = MagicMock()
        creds.valid = True
        creds.expired = True
        creds.refresh_token = "refresh-token"
        flow_cls = MagicMock()
        with patch.dict(sys.modules, _fake_oauthlib_module(flow_cls)):
            with patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                return_value=creds,
            ):
                assert source._auth_oauth(build_obj) is True
        creds.refresh.assert_called_once()
        flow_cls.from_client_config.assert_not_called()

    def test_refresh_failure_falls_back_to_flow(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text("{}")
        creds_file = tmp_path / "client.json"
        creds_file.write_text(json.dumps({"installed": {"client_id": "cid"}}))
        source = GoogleDriveSource(credentials_path=str(creds_file), token_path=token_file)
        build_obj = MagicMock()
        stale = MagicMock()
        stale.valid = False
        stale.expired = True
        stale.refresh_token = "refresh-token"
        stale.refresh.side_effect = Exception("refresh boom")
        new_creds = MagicMock()
        new_creds.to_json.return_value = "{}"
        flow_inst = MagicMock()
        flow_inst.run_local_server.return_value = new_creds
        flow_cls = MagicMock()
        flow_cls.from_client_config.return_value = flow_inst
        with patch.dict(sys.modules, _fake_oauthlib_module(flow_cls)):
            with patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                return_value=stale,
            ):
                assert source._auth_oauth(build_obj) is True
        stale.refresh.assert_called_once()
        flow_cls.from_client_config.assert_called_once()
        build_obj.assert_called_once_with("drive", "v3", credentials=new_creds)

    def test_no_client_id_returns_false(self, tmp_path):
        token_file = tmp_path / "token.json"  # does not exist
        source = GoogleDriveSource(credentials_path=None, token_path=token_file)
        source.credentials_path = None  # override any env-var fallback
        flow_cls = MagicMock()
        with patch.dict(sys.modules, _fake_oauthlib_module(flow_cls)):
            with patch(
                "video_processor.sources.google_drive._DEFAULT_CLIENT_CONFIG",
                {"installed": {"client_id": ""}},
            ):
                assert source._auth_oauth(MagicMock()) is False
        flow_cls.from_client_config.assert_not_called()

    def test_token_load_error_and_bad_config_fall_back_to_flow(self, tmp_path):
        # Existing token that fails to parse + a malformed client-secrets file:
        # both errors are swallowed and the default config drives a fresh flow.
        token_file = tmp_path / "token.json"
        token_file.write_text("not valid json")
        creds_file = tmp_path / "client.json"
        creds_file.write_text("{ broken json")
        source = GoogleDriveSource(credentials_path=str(creds_file), token_path=token_file)
        build_obj = MagicMock()
        new_creds = MagicMock()
        new_creds.to_json.return_value = "{}"
        flow_inst = MagicMock()
        flow_inst.run_local_server.return_value = new_creds
        flow_cls = MagicMock()
        flow_cls.from_client_config.return_value = flow_inst
        with patch.dict(sys.modules, _fake_oauthlib_module(flow_cls)):
            with patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                side_effect=ValueError("corrupt token"),
            ):
                with patch(
                    "video_processor.sources.google_drive._DEFAULT_CLIENT_CONFIG",
                    {"installed": {"client_id": "cid"}},
                ):
                    assert source._auth_oauth(build_obj) is True
        flow_cls.from_client_config.assert_called_once()


class TestGoogleDriveListVideos:
    def test_single_folder_non_recursive(self):
        source = GoogleDriveSource()
        source.service = MagicMock()
        source.service.files.return_value.list.return_value.execute.return_value = {
            "files": [
                {
                    "id": "a",
                    "name": "one.mp4",
                    "size": "1024",
                    "mimeType": "video/mp4",
                    "modifiedTime": "2025-01-01T00:00:00Z",
                },
                {
                    "id": "b",
                    "name": "two.webm",
                    "size": "2048",
                    "mimeType": "video/webm",
                    "modifiedTime": "2025-02-02T00:00:00Z",
                },
            ],
            "nextPageToken": None,
        }
        files = source.list_videos(folder_id="FOLDER", recursive=False)
        assert [f.name for f in files] == ["one.mp4", "two.webm"]
        assert files[0].id == "a"
        assert files[0].size_bytes == 1024
        assert files[0].mime_type == "video/mp4"
        assert files[0].modified_at == "2025-01-01T00:00:00Z"
        assert files[0].path == "one.mp4"
        query = source.service.files.return_value.list.call_args.kwargs["q"]
        assert "'FOLDER' in parents" in query
        assert "trashed=false" in query
        assert "video/mp4" in query

    def test_pagination_follows_next_page_token(self):
        source = GoogleDriveSource()
        source.service = MagicMock()
        source.service.files.return_value.list.return_value.execute.side_effect = [
            {
                "files": [{"id": "a", "name": "p1.mp4", "mimeType": "video/mp4"}],
                "nextPageToken": "PAGE2",
            },
            {
                "files": [{"id": "b", "name": "p2.mp4", "mimeType": "video/mp4"}],
                "nextPageToken": None,
            },
        ]
        files = source.list_videos(folder_id="F", recursive=False)
        assert [f.name for f in files] == ["p1.mp4", "p2.mp4"]
        calls = source.service.files.return_value.list.call_args_list
        assert calls[0].kwargs["pageToken"] is None
        assert calls[1].kwargs["pageToken"] == "PAGE2"

    def test_pattern_filter_excludes_non_matches(self):
        source = GoogleDriveSource()
        source.service = MagicMock()
        source.service.files.return_value.list.return_value.execute.return_value = {
            "files": [
                {"id": "a", "name": "keep.mp4", "mimeType": "video/mp4"},
                {"id": "b", "name": "skip.mkv", "mimeType": "video/x-matroska"},
            ],
            "nextPageToken": None,
        }
        files = source.list_videos(folder_id="F", patterns=["*.mp4"], recursive=False)
        assert [f.name for f in files] == ["keep.mp4"]

    def test_missing_size_is_none(self):
        source = GoogleDriveSource()
        source.service = MagicMock()
        source.service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "a", "name": "nosize.mp4", "mimeType": "video/mp4"}],
            "nextPageToken": None,
        }
        files = source.list_videos(folder_id="F", recursive=False)
        assert files[0].size_bytes is None

    def test_no_folder_id_omits_parents_clause(self):
        source = GoogleDriveSource()
        source.service = MagicMock()
        source.service.files.return_value.list.return_value.execute.return_value = {
            "files": [],
            "nextPageToken": None,
        }
        source.list_videos(folder_id=None, recursive=False)
        query = source.service.files.return_value.list.call_args.kwargs["q"]
        assert "in parents" not in query

    def test_recursive_descends_into_subfolders(self):
        source = GoogleDriveSource()
        source.service = MagicMock()
        # Interleaved: root files, root subfolders, subfolder files, subfolder subfolders.
        source.service.files.return_value.list.return_value.execute.side_effect = [
            {
                "files": [{"id": "r", "name": "root.mp4", "mimeType": "video/mp4"}],
                "nextPageToken": None,
            },
            {"files": [{"id": "subA", "name": "SubA"}], "nextPageToken": None},
            {
                "files": [{"id": "s", "name": "sub.mp4", "mimeType": "video/mp4"}],
                "nextPageToken": None,
            },
            {"files": [], "nextPageToken": None},
        ]
        files = source.list_videos(folder_id="root", recursive=True)
        assert sorted(f.path for f in files) == ["SubA/sub.mp4", "root.mp4"]


class TestGoogleDriveListSubfolders:
    def test_returns_sorted_id_name_tuples(self):
        source = GoogleDriveSource()
        source.service = MagicMock()
        source.service.files.return_value.list.return_value.execute.return_value = {
            "files": [{"id": "2", "name": "Zebra"}, {"id": "1", "name": "Alpha"}],
            "nextPageToken": None,
        }
        result = source._list_subfolders("parent")
        assert result == [("1", "Alpha"), ("2", "Zebra")]
        query = source.service.files.return_value.list.call_args.kwargs["q"]
        assert "application/vnd.google-apps.folder" in query
        assert "'parent' in parents" in query

    def test_pagination_and_no_parent(self):
        source = GoogleDriveSource()
        source.service = MagicMock()
        source.service.files.return_value.list.return_value.execute.side_effect = [
            {"files": [{"id": "1", "name": "A"}], "nextPageToken": "T"},
            {"files": [{"id": "2", "name": "B"}], "nextPageToken": None},
        ]
        result = source._list_subfolders(None)
        assert result == [("1", "A"), ("2", "B")]
        query = source.service.files.return_value.list.call_args_list[0].kwargs["q"]
        assert "in parents" not in query


class TestGoogleDriveDownload:
    def test_download_writes_streamed_content(self, tmp_path):
        source = GoogleDriveSource()
        source.service = MagicMock()

        status = MagicMock()
        status.progress.return_value = 0.5
        # Each entry: (bytes_to_write, status_object, done_flag) per next_chunk() call.
        # First chunk exercises the `if status` progress branch; second (status None)
        # exercises the skip branch and terminates the loop.
        chunk_plan = [(b"hello ", status, False), (b"world", None, True)]

        def media_factory(fh, request):
            state = {"i": 0}
            downloader = MagicMock()

            def next_chunk():
                data, chunk_status, done = chunk_plan[state["i"]]
                state["i"] += 1
                if data:
                    fh.write(data)
                return chunk_status, done

            downloader.next_chunk.side_effect = next_chunk
            return downloader

        f = SourceFile(name="clip.mp4", id="file-42")
        dest = tmp_path / "nested" / "clip.mp4"
        with patch.dict(sys.modules, _fake_http_module(media_factory)):
            result = source.download(f, dest)

        assert result == dest
        assert dest.read_bytes() == b"hello world"
        source.service.files.return_value.get_media.assert_called_once_with(fileId="file-42")
