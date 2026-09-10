# shellcheck shell=sh
# bl-agent-curl.sh — source this once; every curl you then type at a Bain Luck host
# says who you are. Notice 39 / #1916 rung 1.
#
#   . ~/bainluck/tools/bl-agent-curl.sh          # BL_AGENT defaults, with a warning
#   BL_AGENT=bus-hourly . ~/bainluck/tools/bl-agent-curl.sh
#
# ## Why a `curl` SHADOW and not a new command to remember
#
# The traffic this exists to tag is not a program — it is a person-shaped agent typing
# `curl ".../api/events/search?q=Ajax"` into a shell. We know that precisely, because
# the mangled ones are still in the table: over the 7 days to 2026-09-09, 114 of 1,231
# rows in `search_query_logs` carry a backtick or a `**` (`honey deuce`:**`, ``Ajax` ``,
# ``Alcaraz` ``) — markdown that only ever gets into a URL by an agent pasting its own
# notes into a command. Nobody types that. Those 114 are a FLOOR on ad-hoc agent
# traffic, not an estimate of it: they are only the calls clumsy enough to leave a mark.
#
# A helper named `bl_curl` would tag exactly the calls whose author remembered a new
# name — i.e. not the ones above. So this shadows `curl` itself: the command an agent
# already types is the command that carries the tag. (`BL_CURL_NO_SHADOW=1` opts out
# and defines only `bl_curl`.)
#
# ## What the tag DOES — this is not cosmetic labelling
#
# `x-bainluck-origin` is read by `routes/events.py:_request_is_automation`, and any
# non-empty value other than the literal "user" SUPPRESSES the search-query log write
# (`:4038`) and the trending vote (`:6270`). The warmer picks what to warm from the
# 30-day head of that same table, so an untagged probe does not merely add a row — it
# votes, and the warmer then spends real work warming our own specimens.
#
# Two consequences worth stating plainly:
#   * `BL_AGENT=user` is honoured POSITIVELY and keeps the row. Use it when you mean
#     to measure as a person; it is the only value that does not suppress.
#   * Tagging a call that goes somewhere OTHER than the search route is inert today
#     (nothing else reads the header yet). It is still correct to send: a carrier
#     retro-fitted later is a carrier that was missing in every measurement taken
#     in between, and the per-agent counts rung 5 asks for can only ever be as good
#     as the tagging that was running while the traffic happened.
#
#     🔴 It is inert for ATTRIBUTION, and that is the only thing it should ever buy.
#     An earlier draft of this comment justified the tag by saying rung 4 would key
#     the rate-limit allowlist on this header. Do not build that. The value is
#     caller-supplied and forgeable by anyone on the internet, which is precisely
#     what `_router_peer_ip` exists to avoid; `utils/rate_limit.py` says "CEILING,
#     NEVER EXEMPTION" twice in capitals for the same reason. The problem rung 4
#     aimed at was the fleet sharing one 60/min anonymous bucket, and that is
#     already solved by the D70 trusted-ADDRESS ceiling — measured in force on
#     `/api/events/search` on 2026-09-10 (160 requests across two single-window
#     bursts, 0 x 429, confirmed server-side in the router log). A guard test
#     (`test_rate_limiter_does_not_read_the_origin_header`) now fails if anyone
#     wires this header into the limiter.
#
# ## Two things it deliberately refuses to do
#
# 1. **It never sends the header to a host that is not ours.** Our probes also call
#    Kalshi, Polymarket, ESPN and GitHub in the same shells. An internal header naming
#    our lanes has no business on a third party's wire, so the host is PARSED (scheme,
#    userinfo, path and port stripped) and matched as a suffix. A substring test would
#    have tagged `https://example.com/?ref=bainluck.com`.
# 2. **It never sends the header twice.** A request carrying two `x-bainluck-origin`
#    values that disagree about whether its sender is a person is worse than one
#    carrying none: the backend reads `.get()`, i.e. the first, so the caller's explicit
#    intent could silently lose to this file's default. If the caller already passed
#    one, theirs stands and we add nothing.

# The tag is resolved at CALL time, never at source time.
#
# 🔴 The obvious shape — read `BL_AGENT` here and bake it in — ships an EMPTY header,
# and it does it silently. `BL_AGENT=lane . tools/bl-agent-curl.sh` looks like it sets
# the tag, but an assignment prefixed to `.` only persists under POSIX mode; in bash and
# zsh as the lanes run them the value is gone by the time the first curl is typed, and
# `export` of an unset name exports nothing. The wire then carries
# `x-bainluck-origin:` with no value, the backend's `if not raw` reads that as a PERSON,
# and the call votes in the search head exactly as it did before this file existed —
# while the author has every reason to believe it is tagged. Reproduced in both shells
# before this shipped; it is the reason `_bl_curl_agent` exists.
#
# Resolving per call also buys the useful thing: `BL_AGENT=user curl …` as a one-off
# prefix works, because the assignment IS visible for the duration of a function call.
#
# Being unnamed is not evidence of humanity, so an unnamed agent is still tagged. It is
# told once per shell rather than on every call, because the calls this file is for come
# in probe loops and a per-call warning is a warning nobody reads. "Once" has to be
# bookkept by the CALLER: this function runs inside `$( )`, and a flag set in a command
# substitution dies with its subshell — which is how the first draft warned every time.
_bl_curl_agent() {
    # Empty output means "nobody named themselves"; `bl_curl` then adds NOTHING.
    #
    # A BLANK-BUT-SET value normalises to empty, matching `app/utils/agent_origin.py`.
    # Without this, `BL_AGENT="  "` would put `x-bainluck-origin:   ` on the wire, and
    # the backend does NOT read that as absent: `if not raw` passes (the string is
    # truthy), then `raw.strip() != "user"` is true, so the row is suppressed. A value
    # nobody typed on purpose would silently delete the call from the table.
    _bl_v=${BL_AGENT:-}
    if [ -z "$(printf '%s' "$_bl_v" | tr -d '[:space:]')" ]; then
        _bl_v=''
    fi
    printf '%s' "$_bl_v"
}

# Host of a URL-shaped argument, or empty for anything else.
#
# Only arguments that declare a scheme, or that begin with a host we own, are treated
# as URLs at all. That matters because `-d '{"sql":"...bainluck.com..."}'` is an
# ordinary argument in this repo and must never be mistaken for the target.
_bl_curl_host() {
    _bl_a=$1
    case "$_bl_a" in
        http://*|https://*) : ;;
        bainluck.com*|*.bainluck.com*|localhost:*|127.0.0.1:*) : ;;
        *) return 0 ;;
    esac
    _bl_h=${_bl_a#*://}     # scheme
    _bl_h=${_bl_h%%/*}      # path
    _bl_h=${_bl_h%%\?*}     # query, for a scheme-less "host?x"
    _bl_h=${_bl_h##*@}      # userinfo
    _bl_h=${_bl_h%%:*}      # port
    printf '%s' "$_bl_h"
}

_bl_curl_is_ours() {
    case "$1" in
        bainluck.com|*.bainluck.com|localhost|127.0.0.1) return 0 ;;
        *) return 1 ;;
    esac
}

bl_curl() {
    _bl_ours=0
    _bl_tagged=0
    for _bl_arg in "$@"; do
        _bl_host=$(_bl_curl_host "$_bl_arg")
        if [ -n "$_bl_host" ] && _bl_curl_is_ours "$_bl_host"; then
            _bl_ours=1
        fi
        case "$(printf '%s' "$_bl_arg" | tr '[:upper:]' '[:lower:]')" in
            *x-bainluck-origin*) _bl_tagged=1 ;;
        esac
    done

    _bl_who=$(_bl_curl_agent)
    if [ "$_bl_ours" = 1 ] && [ "$_bl_tagged" = 0 ] && [ -z "$_bl_who" ]; then
        # NOTICE 39 GUARD 1: unnamed passes through as PLAIN curl. An earlier
        # draft substituted `agent-unnamed` here, reasoning that being unnamed is
        # not evidence of humanity. True about the world, wrong about the
        # direction of the failure — and the direction is what a default is FOR.
        # Any non-"user" value SUPPRESSES the search-log row server-side, so a
        # substituted default silently deletes every un-configured caller from
        # the table this exists to clean, leaving nothing behind to notice. Not
        # tagging leaves a row we can see and count. `_request_is_automation`
        # picks the same direction for the same reason: it FAILS TOWARD LOGGING.
        if [ -z "${_BL_CURL_WARNED:-}" ]; then
            _BL_CURL_WARNED=1
            printf '%s\n' "bl-agent-curl: BL_AGENT unset, sending this UNTAGGED; set BL_AGENT=<lane-or-mission> to attribute your traffic (BL_AGENT=user to measure as a person)." >&2
        fi
    fi

    if [ "$_bl_ours" = 1 ] && [ "$_bl_tagged" = 0 ] && [ -n "$_bl_who" ]; then
        # Ours go FIRST so a caller's own later -H/-A still wins: curl takes the last
        # User-Agent, and an explicit header from the caller is an explicit intent.
        set -- -H "x-bainluck-origin: $_bl_who" \
               -A "BainLuckBot/1.0 ($_bl_who)" \
               "$@"
    fi

    # No network, no side effect: print the argv this would run, one per line. This is
    # what lets the contract test exercise the REAL decision path in CI.
    if [ -n "${BL_CURL_PRINT:-}" ]; then
        for _bl_arg in "$@"; do printf '%s\n' "$_bl_arg"; done
        return 0
    fi

    command curl "$@"
}

if [ -z "${BL_CURL_NO_SHADOW:-}" ]; then
    curl() { bl_curl "$@"; }
fi
