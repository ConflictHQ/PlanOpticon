# Cloud Sources

PlanOpticon can fetch videos directly from cloud storage services.

## Google Drive

### Service account auth

For automated/server-side usage:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
planopticon batch --source gdrive --folder-id "abc123" -o ./output
```

### OAuth2 user auth

For interactive usage with your own Google account:

```bash
planopticon auth google
planopticon batch --source gdrive --folder-id "abc123" -o ./output
```

### Install

```bash
pip install planopticon[gdrive]
```

## Dropbox

### OAuth2 auth

```bash
planopticon auth dropbox
planopticon batch --source dropbox --folder "/Recordings" -o ./output
```

### Install

```bash
pip install planopticon[dropbox]
```

## All cloud sources

```bash
pip install planopticon[cloud]
```
