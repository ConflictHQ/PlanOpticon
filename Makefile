# Test tiers (docs/contributing.md#test-tiers). Each level runs its tiers and
# fails if the run exceeds the level's time budget, in seconds.
PYTEST ?= python -m pytest
ARGS ?=

# $(call tier,<marker expression>,<budget seconds or 0 for none>)
define tier
	@start=$$(date +%s); \
	$(PYTEST) tests/ -m "$(1)" $(ARGS) || exit $$?; \
	took=$$(( $$(date +%s) - start )); \
	echo "tier run [$(1)] took $${took}s (budget $(2)s)"; \
	if [ "$(2)" != "0" ] && [ $$took -gt $(2) ]; then \
	  echo "over budget: move the slowest tests down a tier"; exit 1; fi
endef

.PHONY: test test-pr test-nightly test-release test-debug

test:  ## always
	$(call tier,always,120)

test-pr:  ## always + sometimes
	$(call tier,always or sometimes,720)

test-nightly:  ## always + sometimes + rarely
	$(call tier,always or sometimes or rarely,4320)

test-release:  ## everything except debug
	$(call tier,not debug,0)

test-debug:  ## one named debug test: make test-debug T=tests/test_x.py::test_y
	@test -n "$(T)" || { echo "usage: make test-debug T=<test node id>"; exit 2; }
	$(PYTEST) "$(T)" -m debug $(ARGS)
