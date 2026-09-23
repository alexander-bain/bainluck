// #925 — the forward-fill that dates what it carries, per field.
//
// The card half of this ship is `independentStateClocks925.test.tsx` (codex's
// reproducer); this file pins the pure helper `OddsChart` calls
// (`lib/chartGameState.ts`). On `origin/master` at 63a9e5880 the module does
// not exist, so this whole file is red there.
//
// The arms that matter are the three-clock ones: every scenario below is a real
// wire shape where one field was observed and another was not, and a single
// shared "state observed at" gets it wrong.

import { carryGameStateForward, type CarriedGameStateRow } from "@/lib/chartGameState";

const T = (mm: string) => `2026-06-15T20:${mm}:00+00:00`;

describe("carryGameStateForward — each field ages on its own clock", () => {
  it("a gap minute inherits the last row's state AND that row's timestamps", () => {
    const rows: CarriedGameStateRow[] = [
      {
        timestamp: T("41"),
        _homeScore: 101,
        _awayScore: 98,
        _period: "4",
        _clock: "1:09",
        _periodObservedAt: T("41"),
        _clockObservedAt: T("41"),
        _scoreObservedAt: T("41"),
      },
      { timestamp: T("42") },
      { timestamp: T("43") },
      {
        timestamp: T("44"),
        _homeScore: 103,
        _awayScore: 98,
        _period: "4",
        _clock: "0:41",
        _periodObservedAt: T("44"),
        _clockObservedAt: T("44"),
        _scoreObservedAt: T("44"),
      },
    ];
    carryGameStateForward(rows);
    expect(rows.map((r) => [r._clock, r._clockApprox, r._clockObservedAt])).toEqual([
      ["1:09", false, T("41")],
      ["1:09", true, T("41")],
      ["1:09", true, T("41")],
      ["0:41", false, T("44")],
    ]);
    // The score is carried too, and dated by its own row.
    expect(rows[2]._homeScore).toBe(101);
    expect(rows[2]._scoreObservedAt).toBe(T("41"));
    expect(rows[2]._scoreApprox).toBe(true);
  });

  it("a PERIOD-only row does not refresh the age of the clock it never saw", () => {
    // The first arm of codex's reproducer, at the helper. A period observation
    // at :03 must leave the clock dated :00 — under one shared stamp the clock
    // silently became "observed at :03" and the card stopped dating it.
    const rows: CarriedGameStateRow[] = [
      { timestamp: T("00"), _period: "1", _clock: "7:41", _periodObservedAt: T("00"), _clockObservedAt: T("00") },
      { timestamp: T("03"), _period: "1", _periodObservedAt: T("03") },
    ];
    carryGameStateForward(rows);
    expect(rows[1]._periodApprox).toBe(false);
    expect(rows[1]._periodObservedAt).toBe(T("03"));
    expect(rows[1]._clock).toBe("7:41");
    expect(rows[1]._clockApprox).toBe(true);
    expect(rows[1]._clockObservedAt).toBe(T("00"));
  });

  it("a CLOCK-only row does not refresh the age of the period it never saw", () => {
    // The second arm. The period is unchanged at "1", which is exactly what
    // makes the bug invisible: the value is right and only its claimed age is
    // wrong, so nothing on screen looks broken.
    const rows: CarriedGameStateRow[] = [
      { timestamp: T("00"), _period: "1", _clock: "7:41", _periodObservedAt: T("00"), _clockObservedAt: T("00") },
      { timestamp: T("03"), _clock: "4:41", _clockObservedAt: T("03") },
    ];
    carryGameStateForward(rows);
    expect(rows[1]._clockApprox).toBe(false);
    expect(rows[1]._clockObservedAt).toBe(T("03"));
    expect(rows[1]._period).toBe("1");
    expect(rows[1]._periodApprox).toBe(true);
    expect(rows[1]._periodObservedAt).toBe(T("00"));
  });

  it("a SCORE-only row refreshes neither (MLB shape: period: null on most rows)", () => {
    const rows: CarriedGameStateRow[] = [
      { timestamp: T("49"), _homeScore: 0, _awayScore: 1, _period: "Top 8th", _periodObservedAt: T("49"), _scoreObservedAt: T("49") },
      { timestamp: T("52"), _homeScore: 0, _awayScore: 1, _scoreObservedAt: T("52") },
      { timestamp: T("53") },
    ];
    carryGameStateForward(rows);
    expect(rows[1]._period).toBe("Top 8th");
    expect(rows[1]._periodObservedAt).toBe(T("49"));
    expect(rows[1]._periodApprox).toBe(true);
    expect(rows[1]._scoreApprox).toBe(false);
    expect(rows[1]._scoreObservedAt).toBe(T("52"));
    // The gap minute after it inherits both, each still on its own clock.
    expect(rows[2]._periodObservedAt).toBe(T("49"));
    expect(rows[2]._scoreObservedAt).toBe(T("52"));
  });

  it("baseball: no clock ever observed, so the clock is never 'approximate'", () => {
    // `_clockApprox` means "this row's clock is inherited". With no clock in
    // the feed there is nothing to be approximate about, and a card that put a
    // `~` on an absent clock would be inventing one.
    const rows: CarriedGameStateRow[] = [
      { timestamp: T("10"), _homeScore: 1, _awayScore: 0, _period: "Top 8th", _periodObservedAt: T("10"), _scoreObservedAt: T("10") },
      { timestamp: T("11") },
    ];
    carryGameStateForward(rows);
    expect(rows[0]._clock).toBeNull();
    expect(rows[0]._clockApprox).toBe(false);
    expect(rows[1]._clock).toBeNull();
    expect(rows[1]._clockApprox).toBe(false);
    expect(rows[1]._clockObservedAt).toBeNull();
    expect(rows[1]._period).toBe("Top 8th");
    expect(rows[1]._periodApprox).toBe(true);
  });

  it("late first observation: rows before it carry nothing and are NOT approximate", () => {
    const rows: CarriedGameStateRow[] = [
      { timestamp: T("30") },
      { timestamp: T("31") },
      { timestamp: T("32"), _homeScore: 2, _awayScore: 0, _period: "2nd Quarter", _periodObservedAt: T("32"), _scoreObservedAt: T("32") },
    ];
    carryGameStateForward(rows);
    expect(rows[0]._periodObservedAt).toBeNull();
    expect(rows[0]._periodApprox).toBe(false);
    expect(rows[0]._scoreObservedAt).toBeNull();
    expect(rows[0]._scoreApprox).toBe(false);
    expect(rows[0]._homeScore).toBeNull();
    expect(rows[0]._clockApprox).toBe(false);
    expect(rows[2]._periodApprox).toBe(false);
  });

  it("an unstamped row dates itself rather than inheriting a wrong stamp", () => {
    // Robustness against a caller that forgets to stamp: the row brought its
    // own period, so it is exact and its own timestamp is the observation. The
    // failure this forbids is silently dating a fresh value by an older row.
    const rows: CarriedGameStateRow[] = [
      { timestamp: T("41"), _period: "3", _periodObservedAt: T("41") },
      { timestamp: T("44"), _period: "4" },
    ];
    carryGameStateForward(rows);
    expect(rows[1]._periodApprox).toBe(false);
    expect(rows[1]._periodObservedAt).toBe(T("44"));
  });

  it("an unchanged price across a gap still carries and dates the state", () => {
    // The price did not move between 20:41 and 20:47; the state must still be
    // there at every minute, dated 20:41 — a flat line is not a blank readout.
    const rows: CarriedGameStateRow[] = [
      { timestamp: T("41"), _period: "3", _clock: "5:00", _periodObservedAt: T("41"), _clockObservedAt: T("41") },
      ...["42", "43", "44", "45", "46", "47"].map((m) => ({ timestamp: T(m) })),
    ];
    carryGameStateForward(rows);
    for (const r of rows.slice(1)) {
      expect(r._period).toBe("3");
      expect(r._clock).toBe("5:00");
      expect(r._clockApprox).toBe(true);
      expect(r._periodApprox).toBe(true);
      expect(r._clockObservedAt).toBe(T("41"));
      expect(r._periodObservedAt).toBe(T("41"));
    }
  });

  it("a one-sided score observation dates the pair by the row that saw it", () => {
    // ESPN sends the side that changed. The readout is "103 - 98" as one
    // string, so it gets one age: the row that observed either half.
    const rows: CarriedGameStateRow[] = [
      { timestamp: T("41"), _homeScore: 101, _awayScore: 98, _scoreObservedAt: T("41") },
      { timestamp: T("44"), _homeScore: 103, _scoreObservedAt: T("44") },
    ];
    carryGameStateForward(rows);
    expect(rows[1]._homeScore).toBe(103);
    expect(rows[1]._awayScore).toBe(98);
    expect(rows[1]._scoreApprox).toBe(false);
    expect(rows[1]._scoreObservedAt).toBe(T("44"));
  });
});
