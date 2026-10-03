import { formatProbabilityPercent } from "../../lib/probabilityDisplay";
import { chanceLabel, compactChange, comparisonPoints, complementQuestion, exactChanceLabel, matrixForStat, quotedChance, resolveQuestion, resolveSource, selectQuestion, sourceKey, type DuringPlayerProps, type DuringPropsRow } from "../../lib/duringPlayerPropsMatrixSelection";

// Synthetic typed projection: these are UI discriminators, not live specimens.
function row(key = "opaque-A", subject = "player-A"): DuringPropsRow {
  return { question_key: key, subject: { key: subject, label: "Same Surname", kind: "player" }, stat_key: "hits", period_key: "full_game",
    predicate: { kind: "count_at_least", count: 2, side: "over", label: "2+" }, complement_question_key: null,
    current: { state: "quoted", probability: .55, basis: "blend_mean", observed_at: "2026-10-02T19:00:00Z" },
    contributors: [{ source: "kalshi", market_id: 10, outcome_id: 20, outcome_name: "Yes", side: "over", period_key: "full_game", probability: .6, observed_at: "2026-10-02T19:00:00Z" }],
    comparison: { state: "comparable", reason: null, baseline: { probability: .4, observed_at: "2026-10-02T18:00:00Z", basis: "pregame_pin" }, delta_points: 15 },
    result: null, _market_id: 10, _market_ids: [10], contributor_outcome_ids: [20] };
}
function data(rows: DuringPropsRow[]): DuringPlayerProps {
  return { contract: "10236.v1", stats: [{ stat_key: "hits", label: "Hits", unit: "hits", unit_singular: "hit", period_key: "full_game", period_label: "Game", predicate: "count_at_least" }], rows,
    coverage: { scope: "linked_markets_loaded_for_event", subjects: 99, questions: 99, quoted: 99, actual_only: 0, unavailable: 0, refused: {} } };
}
describe("During Matrix typed truth", () => {
  test("quoted zero and stale clock survive; actual-only/non-finite/out-of-range do not gain a price", () => {
    const r = row(); r.current.probability = 0; r.current.observed_at = "2020-01-01T00:00:00Z";
    expect(quotedChance(r)).toBe(0); expect(chanceLabel(0)).toBe("0%");
    for (const probability of [null, NaN, Infinity, -0.1, 1.1]) { r.current.probability = probability; expect(quotedChance(r)).toBeNull(); }
    r.current.probability = .8; r.current.state = "actual_only"; expect(quotedChance(r)).toBeNull();
    expect(chanceLabel(.0001)).toBe("<1%"); expect(chanceLabel(.9999)).toBe(">99%");
    // The matrix prints the same number every other surface prints for one value.
    for (const p of [.004, .007, .5, .993, .996]) expect(chanceLabel(p)).toBe(formatProbabilityPercent(p));
    expect(exactChanceLabel(.00000001)).not.toBe("0%");
  });
  test("same labels are distinct subjects and counts come from loaded questions", () => {
    const matrix = matrixForStat(data([row(), row("opaque-B", "player-B")]), "hits");
    expect(matrix.players).toHaveLength(2); expect(matrix.questions).toBe(2);
    expect(matrix.players[0].cells[0]?.question_key).toBe("opaque-A");
  });
  test("source withdrawal never borrows another provider/outcome/side/period", () => {
    const r = row(), selected = r.contributors[0];
    expect(resolveSource(r, selected)).toBe(selected);
    for (const replacement of [{ ...selected, source: "polymarket" }, { ...selected, market_id: 11 }, { ...selected, outcome_id: 21 }, { ...selected, side: "under" as const }]) {
      expect(sourceKey(replacement)).not.toBe(sourceKey(selected)); r.contributors = [replacement]; expect(resolveSource(r, selected)).toBeNull();
    }
  });
  test("question withdrawal never jumps to a similarly named sibling", () => {
    const r = row(), selected = selectQuestion(r);
    expect(resolveQuestion(data([r]), selected)).toBe(r);
    expect(resolveQuestion(data([row("opaque-B"), row("opaque-A", "player-B")]), selected)).toBeNull();
  });
  test("uses server complement key; under-only is reachable without synthesized over or 1-minus quote", () => {
    const over = row(), under = row("server-under");
    under.predicate = { kind: "count_at_most", count: 1, side: "under", label: "1 or fewer" };
    under.current.probability = .3; under.complement_question_key = over.question_key;
    under.contributors = [{ ...over.contributors[0], side: "under", outcome_id: 21, probability: .3 }];
    expect(over.complement_question_key).toBeNull();
    expect(complementQuestion(data([over, under]), over)).toBe(under);
    expect(complementQuestion(data([over, under]), under)).toBe(over);
    expect(quotedChance(complementQuestion(data([over, under]), over)!)).toBe(.3);
    expect(resolveSource(under, over.contributors[0])).toBeNull();
    expect(resolveSource(under, under.contributors[0])?.probability).toBe(.3);
    expect(matrixForStat(data([over, under]), "hits").columns).toHaveLength(1);
    const only = matrixForStat(data([under]), "hits");
    expect(only.columns[0]).toMatchObject({ label: "1 or fewer", underOnly: true });
    expect(only.players[0].cells[0]?.current.probability).toBe(.3);
    expect(only.players[0].cells[0]?.question_key).toBe("server-under");
  });
  test("every served one-way question is reachable, including saved Angel Martínez Hits shape", () => {
    const over = row("s:angel martinez|hits|full_game|ge:1|over", "angel martinez");
    over.subject.label = "Angel Martínez"; over.predicate = { kind: "count_at_least", count: 1, side: "over", label: "1+" }; over.current.probability = .59;
    const under: DuringPropsRow = { ...over, question_key: "s:angel martinez|hits|full_game|le:0|under", predicate: { kind: "count_at_most", count: 0, side: "under", label: "0 or fewer" }, complement_question_key: over.question_key, current: { ...over.current, probability: .41 } };
    const projection = data([over, under]);
    const cells = matrixForStat(projection, "hits").players.flatMap(player => player.cells.filter((cell): cell is DuringPropsRow => cell !== null));
    const reachable = new Set(cells.flatMap(cell => [cell.question_key, complementQuestion(projection, cell)?.question_key]));
    expect(projection.rows.every(question => reachable.has(question.question_key))).toBe(true);
    expect(complementQuestion(projection, over)?.current.probability).toBe(.41);
    expect(complementQuestion(projection, under)?.current.probability).toBe(.59);
  });
  test("reverse relation cannot borrow a different subject/stat/period; ambiguous under rows stay directly reachable", () => {
    const over = row(), under: DuringPropsRow = { ...row("under-A"), predicate: { kind: "count_at_most", count: 1, side: "under", label: "1 or fewer" }, complement_question_key: over.question_key };
    expect(complementQuestion(data([over, { ...under, subject: { ...under.subject, key: "other-player" } }]), over)).toBeNull();
    expect(complementQuestion(data([over, { ...under, stat_key: "rebounds" }]), over)).toBeNull();
    expect(complementQuestion(data([over, { ...under, period_key: "first_half" as "full_game" }]), over)).toBeNull();
    const ambiguous = data([over, under, { ...under, question_key: "under-B", predicate: { kind: "count_at_most", count: 0, side: "under", label: "0 or fewer" } }]);
    expect(complementQuestion(ambiguous, over)).toBeNull();
    const direct = matrixForStat(ambiguous, "hits").players.flatMap(player => player.cells).filter(Boolean).map(cell => cell!.question_key);
    expect(direct).toContain("under-A");
    expect(direct).toContain("under-B");
  });
  test("comparable deltas remain server facts; tiny change omitted only in compact view", () => {
    const r = row(); expect(compactChange(r)).toBe("+15%");
    r.comparison.delta_points = .4; expect(comparisonPoints(r)).toBe(.4); expect(compactChange(r)).toBeNull();
    r.comparison.delta_points = -1.5; expect(compactChange(r)).toBe("−2%");
    r.comparison.state = "unavailable"; expect(comparisonPoints(r)).toBeNull();
  });
  test("unknown/reversed clocks, wrong baseline and mismatch never show a delta", () => {
    const r = row();
    for (const clock of [null, "garbage", "2026-10-02T18:00:00Z", "2026-10-02T17:00:00Z"]) { r.current.observed_at = clock; expect(comparisonPoints(r)).toBeNull(); }
    r.current.observed_at = "2026-10-02T19:00:00Z";
    r.comparison.reason = "contributor_set_mismatch"; expect(comparisonPoints(r)).toBeNull();
    r.comparison.reason = null; r.comparison.baseline = null; expect(comparisonPoints(r)).toBeNull();
  });
  test("empty statistic and unsupported contract stay unavailable", () => {
    expect(matrixForStat(data([row()]), "yards").players).toEqual([]);
    expect(matrixForStat(null, "hits").players).toEqual([]);
  });
});
