#!/usr/bin/env bash
#
# tray.sh — say what is actually in a runner inbox, by STATE, and make "empty" a
#           claim the tool MAKES rather than a silence the reader interprets.
#
#   usage:  tools/tray.sh <inbox-dir>        one inbox
#           tools/tray.sh --all [<root>]     every inbox under runner-inbox/
#           tools/tray.sh --strict <dir>     an undefined suffix also exits 1
#           tools/tray.sh --dry-run          self-test: classifier + verdict/exit agreement
#           tools/tray.sh --help
#
#   exit 0  inspected, nothing PENDING — the tray is clear of work
#   exit 1  a result: something is PENDING (or, under --strict, undefined)
#   exit 2  the tool could not answer (bad usage, unreadable directory)
#
#   A PIPE EATS THE EXIT CODE (gotcha #54). `tray.sh <dir> | tail` leaves `$?`
#   holding TAIL's zero, which reads as CLEAR next to a NOT CLEAR verdict — int364
#   hit this on the tool's first real run at the desk. So every VERDICT and FLEET
#   line ENDS with the code it is about to return, `(exit N)`. Piped or not, read
#   the line: it carries the same bit as `$?` on a channel a pipe cannot eat.
#
# ── WHY THIS IS A FILE (int363 → latency/414, 2026-09-14 23:52Z) ─────────────
#
# Today the desk called its tray EMPTY and there were EIGHT pending offers in
# it. The read was `ls | grep -E '\.md$'` → 0; `find . -maxdepth 1 -type f
# -name '*.md'` → 8, in the same directory, in the same second. Four of the
# eight were merged only because an independent open-PR-state sweep caught them;
# two were caught only because calibration/1234's ledger row said "my offer WAS
# in the tray when the desk swept it empty" and the desk re-read the directory.
# int362, one pass earlier, is stamped eight minutes after an offer file was
# written and also said EMPTY.
#
# The failure is not the grep. It is that **a listing which silently returns
# nothing is indistinguishable from an empty tray** — the same shape as
# `60063216b` (a registry guard counting a filesystem instead of what git
# tracks) and `43e95189c` (the scratch trees that made it count 4,798 phantoms).
# A reader counting the directory instead of asserting about it. So this prints
# a verdict line every single time, including on the empty case, and it exits
# non-zero the moment a human is owed something.
#
# ── IT RUNS UNDER bash, AND EVERY `grep` IS `/usr/bin/grep` ──────────────────
#
# Notice 44 / #5037: in a lane's interactive shell `grep` is a function wrapping
# ugrep 7.8.4 whose `-qv` is the bit-flip of `-q`. A `#!` script never sources
# that snapshot, so this file is already safe; the explicit path is here so a
# line copied OUT of it into a lane shell stays safe too. There is in fact no
# `grep` left in the classifier at all — it is pure bash string work on the
# filename, which is the only input — but the discipline is stated because the
# next edit is where it would come back.
#
# Enumeration is `find -maxdepth 1 -type f`, never `ls`: `ls` pipes a
# human-formatted listing, sorts, and on some builds colourises, and every one
# of those is a way for a filename to stop matching a pattern that describes it.
#
# ── THE STATE VOCABULARY IS AN OPEN SET, AND THAT IS WHY UNKNOWN IS A CLASS ──
#
# The disposition suffixes below were MEASURED across all 5,800-odd dispositioned
# notes under `runner-inbox/` on 2026-09-15, not copied from a protocol doc:
# consumed 5160, resolved 205, superseded 182, noted 112, fails 54, read 28,
# answered 20, bounced 18, honoured 10, stale 9, running 9, held 7, routed 6,
# withdrawn 7 (4 + 3 upper-case), refused 4, void 2, overtaken 2, discharged 2,
# trayed 1, and a dozen one-offs.
#
# Notice 11 says a file that is "neither pending, .running, .consumed, .failed
# nor .superseded is an orphan by definition — mark it, don't guess." That list
# is five of the twenty-odd states actually in use, so applying it literally
# would report hundreds of correctly-dispositioned notes as orphans and the tool
# would be ignored by its second run. The rule this file takes from the notice
# is the one that survives deleting its case: **do not guess.** So an unknown
# suffix is reported AS UNKNOWN, by name, in its own class — never silently
# folded into "done" and never miscounted as "pending". A state that
# turns out to be real gets added to KNOWN_STATES in a one-line diff, which is
# how the vocabulary is allowed to grow deliberately instead of by inference.
#
# ── WHAT IT DOES NOT DO ──────────────────────────────────────────────────────
#
# It does not read a note, judge it, or act on it. "Is this offer mergeable" is
# `tools/merge-gate.sh`; "is this sha already on master" is
# `git merge-base --is-ancestor` (notice 31). This answers one question —
# what is in this directory and what state is each thing in — because that is
# the question that was answered wrongly twice today.
#
# It also cannot tell you about an offer that was never written. Notice 31(b)'s
# ledger × ancestry sweep is the instrument for that and this is not a
# substitute for it: a clear tray here means the directory is clear, which is a
# smaller claim than "nothing is waiting."

set -u -o pipefail

# Terminal states, measured (see the header). `running` is deliberately NOT in
# here — it is in-flight, which is neither pending nor done, and it gets its own
# line so a reader can see a claim that has been held too long.
KNOWN_STATES="consumed resolved superseded noted fails failed read answered bounced honoured honored stale held routed withdrawn refused void overtaken discharged trayed actioned abandoned moot hold missed"
IN_FLIGHT_STATES="running"

# Case-insensitive `case`/`[[` matching, which is how `WITHDRAWN`, `TRAYED` and
# `MISSED` are recognised as the same states as their lower-case siblings without
# a `tr` fork per segment. It is set once, at the top, deliberately: a `shopt`
# toggled around a hot loop is the kind of global that outlives the loop.
shopt -s nocasematch

# Prints the header block above, from the title to the first `# ──` banner. The
# range is delimited, not numbered: the first draft said `3,13p` and this very
# edit — four lines added above it — would have silently truncated the usage text
# to nothing a reader would notice, which is the tool's own failure mode.
usage() {
    /usr/bin/sed -n '3,${/^# ──/q; s/^# \{0,1\}//; p;}' "${BASH_SOURCE[0]}"
}

# ── THE HOT PATH IS FORK-FREE ON PURPOSE ─────────────────────────────────────
#
# These set globals instead of echoing, and the enumerator uses `${f##*/}` rather
# than `basename`. The first draft used `$(...)` for the token, the state fold
# and the basename — four forks per file — and `--all` over the fleet's ~20,000
# notes did not finish in two minutes. A sweep tool nobody will wait for is a
# sweep tool nobody runs, which is the failure this file exists to end.
_TOKEN=""
_STATE=""
_CLASS=""
_DETAIL=""

# The leading word of a suffix segment: `consumed-2335Z-lat413-ACK` → `consumed`.
_token() {
    _TOKEN="${1%%-*}"
    _TOKEN="${_TOKEN%%_*}"
}

_is_known()     { case " $KNOWN_STATES "     in *" $1 "*) return 0 ;; esac; return 1; }
_is_in_flight() { case " $IN_FLIGHT_STATES " in *" $1 "*) return 0 ;; esac; return 1; }

# The LAST recognised state token among dot-separated segments, or "".
#
# `.md.running.consumed-2335Z-…` is a real shape in this directory — a claim that
# was later discharged — so segments are walked in order and the LAST recognised
# one wins. Reading only the first files a finished note under `running` forever.
#
# The splitter is parameter expansion, not `IFS=. read -ra`. An earlier draft set
# `local IFS='.'` around the loop and every lookup inside `_is_known` then split
# ITS OWN word list on dots — bash scopes `local` dynamically, so the helper
# inherited the caller's IFS and silently matched nothing. Nine of fifteen
# self-test cases caught it; a hand-run against a real directory would not have,
# because "no state recognised" reads as a plausible answer. Touching IFS at all
# in a file whose whole job is reading names is a hazard, so it is not touched.
_last_state() {
    local rest="$1" seg
    _STATE=""
    while [ -n "$rest" ]; do
        case "$rest" in
            *.*) seg="${rest%%.*}"; rest="${rest#*.}" ;;
            *)   seg="$rest";       rest="" ;;
        esac
        [ -n "$seg" ] || continue
        _token "$seg"
        if _is_known "$_TOKEN" || _is_in_flight "$_TOKEN"; then _STATE="$_TOKEN"; fi
    done
}

# Classify one BASENAME into `_CLASS` / `_DETAIL`.
_classify() {
    local name="$1"

    case "$name" in
        *.md)
            _CLASS=PENDING; _DETAIL='-'; return ;;
        *.md.*)
            _last_state "${name#*.md.}"
            if [ -z "$_STATE" ]; then
                _token "${name#*.md.}"; _CLASS=UNKNOWN; _DETAIL="$_TOKEN"
            elif _is_in_flight "$_STATE"; then
                _CLASS=IN-FLIGHT; _DETAIL="$_STATE"
            else
                _CLASS=DONE; _DETAIL="$_STATE"
            fi
            return ;;
        *)
            # No `.md` anywhere. The inbox holds a handful of these and some ARE
            # dispositioned (`…-CERT-2695-2b437bae.WITHDRAWN-0850Z-…`), so the
            # same scan is applied before giving up — otherwise the tool reports
            # a closed item as a stray and a reader re-opens it.
            _last_state "${name#*.}"
            if [ -z "$_STATE" ]; then
                _CLASS=NOT-A-NOTE; _DETAIL="${name##*.}"
            elif _is_in_flight "$_STATE"; then
                _CLASS=IN-FLIGHT; _DETAIL="$_STATE (no .md in the name)"
            else
                _CLASS=DONE; _DETAIL="$_STATE (no .md in the name)"
            fi
            return ;;
    esac
}

# The self-test's view of `_classify`, and the only place a fork per name is
# affordable. Echoes "<class>\t<detail>".
classify() {
    _classify "$1"
    printf '%s\t%s\n' "$_CLASS" "$_DETAIL"
}

# _verdict_exit <code> <printf-fmt-without-newline> [args…] — print the line with
# `(exit <code>)` welded to its end, then return that same code. One argument,
# used twice, so the sentence a piped reader gets and the code a scripted reader
# gets cannot disagree.
_verdict_exit() {
    local code="$1" fmt="$2"
    shift 2
    # shellcheck disable=SC2059  # fmt is a literal from this file, never input
    printf "$fmt (exit %d)\n" "$@" "$code"
    return "$code"
}

# Returns 0 clear, 1 needs-a-human. Prints one block.
scan_dir() {
    local dir="$1" quiet="${2:-0}" strict="${STRICT:-0}"
    local pending=() inflight=() unknown=() other=() done_n=0

    if [ ! -d "$dir" ]; then
        _verdict_exit 2 'TRAY %s :: UNREADABLE — not a directory. This is NOT an empty tray.' "$dir"
        return $?
    fi

    # `${f##*/}`, not `basename` — see the fork-free note above. `read -r` with an
    # empty IFS so a filename holding a space or a tab survives intact, and
    # process substitution rather than a pipe so the counters below are this
    # shell's and not a subshell's (the classic `while read | count` zero).
    local f base n=0
    while IFS= read -r f; do
        base="${f##*/}"
        case "$base" in .*) continue ;; esac          # editor and OS droppings
        n=$((n + 1))
        _classify "$base"
        case "$_CLASS" in
            PENDING)    pending[${#pending[@]}]="$base" ;;
            IN-FLIGHT)  inflight[${#inflight[@]}]="$base" ;;
            UNKNOWN)    unknown[${#unknown[@]}]="$base  [suffix: $_DETAIL]" ;;
            NOT-A-NOTE) other[${#other[@]}]="$base  [.$_DETAIL]" ;;
            DONE)       done_n=$((done_n + 1)) ;;
        esac
    done < <(find "$dir" -maxdepth 1 -type f 2>/dev/null)

    local np=${#pending[@]} ni=${#inflight[@]} nu=${#unknown[@]} no=${#other[@]}
    local notes_n=$n

    printf 'TRAY %s :: files=%d  PENDING=%d  in-flight=%d  unknown-suffix=%d  dispositioned=%d  not-a-note=%d\n' \
        "$dir" "$notes_n" "$np" "$ni" "$nu" "$done_n" "$no"

    if [ "$quiet" = "0" ]; then
        local x
        for x in "${pending[@]-}";  do [ -n "$x" ] && printf '  PENDING    %s\n' "$x"; done
        for x in "${inflight[@]-}"; do [ -n "$x" ] && printf '  IN-FLIGHT  %s\n' "$x"; done
        for x in "${unknown[@]-}";  do [ -n "$x" ] && printf '  UNKNOWN    %s\n' "$x"; done
        for x in "${other[@]-}";    do [ -n "$x" ] && printf '  NOT-A-NOTE %s\n' "$x"; done
    fi

    # ── WHAT SETS EXIT 1, AND WHY AN UNKNOWN SUFFIX DOES NOT (by default) ────
    #
    # Measured before choosing: across all 7,121 notes in the fleet there are
    # exactly THREE unknown suffixes, and all three are one-off human inventions
    # on notes that are plainly finished (`.NOT-TAKEN-0010Z-…`,
    # `.orphan-by-218-…`, `.notice30-copy`). Counting them toward exit 1 would
    # leave two otherwise-clear trays permanently red, and a red that never goes
    # green is how a reader learns to stop reading the exit code — which is the
    # failure that produced the eight-offer tray in the first place. So the
    # DEFAULT answers the desk's actual question, "is anyone owed an action",
    # and the hygiene item is printed, named and counted in the header without
    # setting the code. `--strict` is there for a reader who wants it to count.
    #
    # Every branch below states its own exit code in the printed line. See the
    # pipe note in the header: `$?` is not a channel this tool can rely on
    # reaching its reader, and a verdict whose text a pipe preserves while its
    # code is silently replaced is the same defect as a listing that returns
    # nothing. `_verdict_exit` keeps the printed number and the returned one from
    # ever drifting apart — they are one argument, used twice.
    if [ "$np" -gt 0 ] || { [ "$strict" = "1" ] && [ "$nu" -gt 0 ]; }; then
        _verdict_exit 1 'VERDICT %s :: NOT CLEAR — %d pending, %d unknown-suffix. Read them before you call this tray empty.' \
            "$dir" "$np" "$nu"
        return $?
    fi
    if [ "$nu" -gt 0 ]; then
        _verdict_exit 0 'VERDICT %s :: CLEAR of pending work — but %d file(s) wear a suffix nobody defined (named above). Hygiene, not an action; `--strict` makes it exit 1.' \
            "$dir" "$nu"
        return $?
    fi
    _verdict_exit 0 'VERDICT %s :: CLEAR — every file carries a disposition. (This is a claim about the DIRECTORY, not about whether an offer went unwritten — notice 31(b).)' "$dir"
    return $?
}

# ── self-test ────────────────────────────────────────────────────────────────
#
# This is the `--dry-run` line notice 10's SCRIPTS/LAUNCHER clause asks for AND
# the guard test for the classifier, in one place, so the diff stays under
# `tools/**` and forces no Heroku release. Every case below is a real filename
# shape taken from `runner-inbox/` today, including the chained
# `.md.running.consumed-…` that a first-token reader gets wrong.
dry_run() {
    local fails=0 got want name
    run_case() {
        name="$1"; want="$2"
        got="$(classify "$name")"
        got="${got%%$'\t'*}"
        if [ "$got" = "$want" ]; then
            printf '  ok    %-10s %s\n' "$got" "$name"
        else
            printf '  FAIL  want=%-10s got=%-10s %s\n' "$want" "$got" "$name"
            fails=$((fails + 1))
        fi
    }

    printf 'tray.sh --dry-run :: self-test — classifier on names, then verdict/exit agreement on a throwaway tree\n'
    run_case 'FROM-latency-413-2327Z-ROW-CLEAR-asking-for-the-next-one.md'            PENDING
    run_case 'RESTOCK-20260914-155500.md'                                              PENDING
    run_case 'FROM-x.md.consumed-2315Z-int363-MERGED-96bf28663'                        DONE
    run_case 'FROM-x.md.resolved-2247Z-int363-YOU-ARE-RIGHT'                           DONE
    run_case 'FROM-x.md.noted-2315Z-int363-your-sha-was-MERGED'                        DONE
    run_case 'FROM-x.md.held-2248Z-int363-CORRECT-not-an-offer'                        DONE
    run_case 'FROM-x.md.answered-2215Z-int362-ROW-ASSIGNED'                            DONE
    run_case 'FROM-x.md.superseded-0608Z-by-lat392-restock'                            DONE
    run_case 'FROM-x.md.TRAYED-2318Z-int363-GATE-GO-at-b9279c54f'                      DONE
    run_case 'TRAYED-by-int320-0820Z-CERT-2695.WITHDRAWN-0850Z-premise-false'          DONE
    run_case 'RESTOCK-20260914-151826.md.running'                                      IN-FLIGHT
    run_case 'FROM-x.md.running.consumed-2335Z-lat413-ACK-row-CLEAR'                   DONE
    run_case 'FROM-x.md.bananas-1200Z-someone-invented-a-state'                        UNKNOWN
    run_case 'notes.txt'                                                               NOT-A-NOTE
    run_case 'PARKED-MEASUREMENTS'                                                     NOT-A-NOTE

    # ── the printed code and the returned code are one claim ─────────────────
    #
    # `(exit N)` exists because a pipe eats `$?`, so a reader who can only see
    # the TEXT must be able to trust it. That trust is exactly what drifts the
    # first time someone adds a branch and copies the wrong literal, and it
    # drifts SILENTLY — the tool keeps printing a number and the number is
    # wrong, which is worse than the pipe. So each verdict branch is run for
    # real, against a throwaway tree, and the number in the sentence is compared
    # with the number the function actually returned. A temp directory is the
    # one bit of I/O in here and it buys the whole guarantee.
    local tmp
    tmp="$(mktemp -d "${TMPDIR:-/tmp}/tray-dryrun.XXXXXX")" || {
        printf '  FAIL  could not create a temp tree for the verdict cases\n'
        return 1
    }

    verdict_case() {
        local label="$1" dir="$2" want_rc="$3" want_text="$4"
        local out rc printed
        out="$(scan_dir "$dir" 1)"; rc=$?
        printed="${out##*"(exit "}"; printed="${printed%%)*}"
        if [ "$rc" = "$want_rc" ] && [ "$printed" = "$want_rc" ] && [[ "$out" == *"$want_text"* ]]; then
            printf '  ok    exit %s   %s\n' "$rc" "$label"
        else
            printf '  FAIL  %s: returned=%s printed=%s want=%s (text %s)\n' \
                "$label" "$rc" "$printed" "$want_rc" \
                "$([[ "$out" == *"$want_text"* ]] && printf 'ok' || printf "missing '$want_text'")"
            fails=$((fails + 1))
        fi
    }

    mkdir -p "$tmp/clear" "$tmp/pending" "$tmp/unknown"
    : > "$tmp/clear/FROM-x.md.consumed-0100Z-int364-MERGED"
    : > "$tmp/pending/FROM-latency-414-0055Z-GATE-GO.md"
    : > "$tmp/unknown/FROM-x.md.bananas-1200Z-someone-invented-a-state"

    verdict_case 'clear tray'                "$tmp/clear"       0 'CLEAR — every file'
    verdict_case 'one pending offer'         "$tmp/pending"     1 'NOT CLEAR'
    verdict_case 'unknown suffix, default'   "$tmp/unknown"     0 'CLEAR of pending work'
    # Set and unset around the call, never `STRICT=1 verdict_case …`: an
    # assignment prefixed to a FUNCTION call is not reliably scoped to it, and a
    # leak here would silently re-grade every later case.
    STRICT=1
    verdict_case 'unknown suffix, --strict'  "$tmp/unknown"     1 'NOT CLEAR'
    unset STRICT
    verdict_case 'directory that is not one' "$tmp/no-such-dir" 2 'UNREADABLE'

    # The usage text is printed by a delimited `sed` range over this very file;
    # a range that stops matching prints NOTHING and `--help` fails open silent.
    local help_text
    help_text="$(usage)"
    if [[ "$help_text" == *'exit 1'* ]] && [[ "$help_text" == *'PIPE EATS'* ]]; then
        printf '  ok    %-10s usage block still reaches the exit codes and the pipe note\n' 'help'
    else
        printf '  FAIL  usage block is truncated or empty (%d chars) — check the sed range\n' "${#help_text}"
        fails=$((fails + 1))
    fi

    case "$tmp" in */tray-dryrun.*) rm -rf "$tmp" ;; esac

    if [ "$fails" -eq 0 ]; then
        printf 'tray.sh --dry-run :: 21/21 OK, exit 0\n'
        return 0
    fi
    printf 'tray.sh --dry-run :: %d FAILED\n' "$fails"
    return 1
}

# ── main ─────────────────────────────────────────────────────────────────────

main() {
    local quiet=0
    # `--strict` is consumed here and passed on through the environment, so it
    # composes with `--all` and with a bare directory alike.
    while [ "${1:-}" = "--strict" ] || [ "${1:-}" = "--quiet" ]; do
        [ "$1" = "--strict" ] && export STRICT=1
        [ "$1" = "--quiet" ] && quiet=1
        shift
    done
    case "${1:-}" in
        ''|-h|--help)  usage; return 2 ;;
        --dry-run)     dry_run; return $? ;;
        --all)
            local root="${2:-$HOME/bainluck/.claude/handoff/runner-inbox}"
            if [ ! -d "$root" ]; then
                _verdict_exit 2 'ROOT %s :: UNREADABLE — not a directory. This is NOT an empty fleet.' "$root"
                return $?
            fi
            local rc=0 d sub
            while IFS= read -r d; do
                scan_dir "$d" 1 || { sub=$?; [ "$sub" -gt "$rc" ] && rc=$sub; }
            done < <(find "$root" -maxdepth 1 -mindepth 1 -type d | sort)
            _verdict_exit "$rc" 'FLEET %s :: %s' "$root" \
                "$([ "$rc" -eq 0 ] && printf 'every inbox CLEAR' || printf 'at least one inbox NOT CLEAR — re-run it without --all for the filenames')"
            return $? ;;
    esac
    [ $# -eq 1 ] || { usage; return 2; }
    scan_dir "$1" "$quiet"
}

main "$@"
