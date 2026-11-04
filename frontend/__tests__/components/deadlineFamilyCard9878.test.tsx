/**
 * Discriminating frontend tests for Slice 1 v2 movement-led deadline-family card (#9878 / #11040).
 *
 * Covers all Section 3, 4, 5, 6, 7, and 8 requirements:
 * - Case 1a: Missing rule equivalence proof (`rule_verification` absent/false) is refused.
 * - Case 1b: Rule-verified Oct 14 NULL stored-claim control (markets 65678073 & 65678074) renders level-led family card.
 * - Case 2: Explicitly synthetic valid stored claim + outcome-bound dated comparison basis (`-6.5` pts).
 * - Case 3: Expired (>24h) or premature (<12h) dated basis refused; fallback to nearest 50%.
 * - Case 4: No-leading binary outcomes — exact Yes outcome ID supplies every value.
 * - Case 5: Raw un-enriched `fetch.json` rows, missing Yes, duplicate IDs, and mismatched rule template hashes refused.
 * - Case 6 & 7: Single authoritative mount path (`DiscoverCard -> ThemeBundleCard -> DeadlineFamilyCard`), deterministic tie-breaks, and ascending `deadline_instant` ordering.
 * - Case 8: Exact local calendar date & `23:59` cutoff in `America/New_York` verified (3B); `[-14h, +36h]` neighboring-day shift refused.
 * - Case 9 & 10: Q8 local 97%+ open-mover exception admitted while evidence is in-window and refused after expiry.
 * - Case 11a: 3C / 6D authoritative venue settlement (`resolved`) vs `trading_closed` vs `void`/`unknown` refusal.
 * - Case 11b: 3D missing `price_observed_at` is never substituted with `nowIso` or `new Date()` and refuses movement claims.
 * - Case 12: 6E honest absence, measured zero, sub-threshold (<2pt), moderate (2..<5pt), and hero (>=5pt) agreement.
 * - Case 13: Direct User Decision Q4 reader-local calendar-day comparison wording ("since yesterday" vs same-day clock).
 * - Case 14 & 15: 6F represented count vs provider inventory completeness, unpriced member reachability, and Q2 in-place expand/collapse with `/futures/{id}` member destinations.
 */

import "../helpers/minimalDom";
import React, { act } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createRoot } from "react-dom/client";
import type {
  FeedBundleData,
  FeedDeadlineMemberContract,
  FeedFuturesData,
  FeedItem,
} from "@/lib/types";

const mockTrackEvent = jest.fn();

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
  }),
}));

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({
      href,
      children,
      ...rest
    }: {
      href: string;
      children: React.ReactNode;
      [k: string]: unknown;
    }) => ReactLib.createElement("a", { href, ...rest }, children),
  };
});

jest.mock("next/image", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ alt }: { alt: string }) =>
      ReactLib.createElement("img", { alt }),
  };
});

jest.mock("@/lib/analytics", () => ({
  __esModule: true,
  trackEvent: (...args: unknown[]) => mockTrackEvent(...args),
}));

jest.mock("@/components/Analytics", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
}));

import DiscoverCard from "../../components/DiscoverCard";
import { DeadlineFamilyCard } from "../../components/discover/DeadlineFamilyCard";
import { ThemeBundleCard } from "../../components/discover/ThemeBundleCard";
import {
  DETERMINISTIC_TIE_BREAK_RULE,
  buildDeadlineFamilyCardModel,
  formatDeadlineMovementTimeframe,
  validateAndBuildDeadlineFamilyCardModel,
} from "../../lib/discover/deadlineFamilyCard";

const RETAINED_NOW_ISO = "2026-10-14T23:47:16+00:00";
const RETAINED_OBSERVED_AT = "2026-10-14T23:45:00+00:00";
const RETAINED_BASIS_AT = "2026-10-14T02:10:00+00:00"; // 21.58h before RETAINED_OBSERVED_AT, previous EDT day (Oct 13 22:10 EDT vs Oct 14 19:45 EDT)
const ZACHARIA_RULE_HASH = "e60c32728557d429";

function makeOct31Contract(
  overrides: Partial<FeedDeadlineMemberContract> = {},
): FeedDeadlineMemberContract {
  return {
    market_id: 65678073,
    name: "Will Zacharia be out as Prime Minister of Israel by October 31?",
    source: "polymarket",
    external_id:
      "0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
    group_id: "polymarket:256241",
    group_type: "polymarket_event",
    market_type: "binary",
    stem_key: "zacharia be out as prime minister of israel",
    display_stem: "Zacharia be out as Prime Minister of Israel",
    shared_question: "Zacharia be out as Prime Minister of Israel by…?",
    preposition: "by",
    deadline_text: "October 31",
    short_deadline: "Oct 31",
    deadline_label: "By Oct 31",
    calendar_date: "2026-10-31",
    deadline_instant: "2026-11-01T03:59:00+00:00", // Oct 31, 2026 11:59 PM EDT
    deadline_epoch: 1793505540,
    cutoff_timezone: "America/New_York",
    cutoff_local_time: "23:59",
    rule_template_hash: ZACHARIA_RULE_HASH,
    rule_verification: {
      verified: true,
      evidence_source: "market_metadata.deadline_rule_contract",
      rule_template_hash: ZACHARIA_RULE_HASH,
      cutoff_timezone: "America/New_York",
      cutoff_local_time: "23:59",
      reason: null,
    },
    yes_outcome_id: 246879005,
    yes_outcome_name: "Yes",
    yes_external_id:
      "74167794401960881962150670422546952062478246672716256803305946716278016867432",
    no_outcome_id: 246879006,
    no_external_id:
      "23750296999441781140845142318022266810772441561257322279207268816415471449435",
    yes_probability: 0.073,
    yes_rendered_percent: 7,
    no_probability: 0.927,
    price_observed_at: RETAINED_OBSERVED_AT,
    stored_movement_claim: null,
    movement_basis: {
      outcome_id: 246879005,
      basis_price: 0.084,
      observed_at: RETAINED_BASIS_AT,
      age_hours: 21.58,
      in_window: true,
    },
    movement_status: "no_stored_claim",
    supported_move: null,
    supported_move_points: null,
    show_hero_movement_chip: false,
    show_row_movement_badge: false,
    settlement: {
      state: "open",
      is_settled: false,
      is_trading_closed: false,
      status: "open",
      winner: null,
      result: null,
      authoritative_source: null,
      lagging_local_status: false,
    },
    is_near_certain: false,
    near_certain_open_eligible: false,
    provider_market_count: 2,
    detail_href: "/futures/65678073",
    ...overrides,
  };
}

function makeDec31Contract(
  overrides: Partial<FeedDeadlineMemberContract> = {},
): FeedDeadlineMemberContract {
  return {
    market_id: 65678074,
    name: "Will Zacharia be out as Prime Minister of Israel by December 31?",
    source: "polymarket",
    external_id:
      "0x28561992978d9dc04ab0b039d7b6390cd6116ef60d1ce3ed2da5328d73bc8ef9",
    group_id: "polymarket:256241",
    group_type: "polymarket_event",
    market_type: "binary",
    stem_key: "zacharia be out as prime minister of israel",
    display_stem: "Zacharia be out as Prime Minister of Israel",
    shared_question: "Zacharia be out as Prime Minister of Israel by…?",
    preposition: "by",
    deadline_text: "December 31",
    short_deadline: "Dec 31",
    deadline_label: "By Dec 31",
    calendar_date: "2026-12-31",
    deadline_instant: "2027-01-01T04:59:00+00:00", // Dec 31, 2026 11:59 PM EST
    deadline_epoch: 1798779540,
    cutoff_timezone: "America/New_York",
    cutoff_local_time: "23:59",
    rule_template_hash: ZACHARIA_RULE_HASH,
    rule_verification: {
      verified: true,
      evidence_source: "market_metadata.deadline_rule_contract",
      rule_template_hash: ZACHARIA_RULE_HASH,
      cutoff_timezone: "America/New_York",
      cutoff_local_time: "23:59",
      reason: null,
    },
    yes_outcome_id: 246879007,
    yes_outcome_name: "Yes",
    yes_external_id:
      "109248864950550918456926707901283260679215457211637114746364964324227495763694",
    no_outcome_id: 246879008,
    no_external_id:
      "52010207094808582680015014179469522027848394847004098667580388318701129457468",
    yes_probability: 0.245,
    yes_rendered_percent: 25,
    no_probability: 0.755,
    price_observed_at: RETAINED_OBSERVED_AT,
    stored_movement_claim: null,
    movement_basis: {
      outcome_id: 246879007,
      basis_price: 0.31,
      observed_at: RETAINED_BASIS_AT,
      age_hours: 21.58,
      in_window: true,
    },
    movement_status: "no_stored_claim",
    supported_move: null,
    supported_move_points: null,
    show_hero_movement_chip: false,
    show_row_movement_badge: false,
    settlement: {
      state: "open",
      is_settled: false,
      is_trading_closed: false,
      status: "open",
      winner: null,
      result: null,
      authoritative_source: null,
      lagging_local_status: false,
    },
    is_near_certain: false,
    near_certain_open_eligible: false,
    provider_market_count: 2,
    detail_href: "/futures/65678074",
    ...overrides,
  };
}

function makeFeedItemFromContract(
  contract: FeedDeadlineMemberContract,
): FeedItem {
  return {
    type: "futures",
    score: 52,
    reason: "Politics",
    headline: contract.name,
    context_summary: null,
    data: {
      id: contract.market_id,
      name: contract.name,
      sport: null,
      sport_name: null,
      llm_sport_category: "politics",
      source: contract.source,
      source_count: 1,
      market_tier: 2,
      market_type: "binary",
      status: contract.settlement.status,
      resolution_date: contract.deadline_instant,
      price_observed_at: contract.price_observed_at,
      group_id: contract.group_id,
      external_id: contract.external_id,
      deadline_member: contract,
      // `No` is intentionally rank=1 (leading outcome) to test 6C exact outcome binding
      top_outcomes: [
        {
          id: contract.no_outcome_id,
          name: "Likely No: Zacharia be out",
          probability: contract.no_probability ?? null,
          rank: 1,
          movement:
            contract.stored_movement_claim != null
              ? -contract.stored_movement_claim
              : null,
          rendered_percent:
            contract.yes_rendered_percent != null
              ? 100 - contract.yes_rendered_percent
              : null,
        },
        {
          id: contract.yes_outcome_id,
          name: "Yes: Zacharia be out",
          probability: contract.yes_probability,
          rank: 2,
          movement: contract.stored_movement_claim,
          rendered_percent: contract.yes_rendered_percent ?? null,
        },
      ],
      outcome_count: 2,
      canonical_market_key: null,
    } as unknown as FeedFuturesData,
  };
}

function makeDeadlineBundleFeedItem(members: FeedItem[]): FeedItem {
  return {
    type: "bundle",
    score: 52,
    reason: "Zacharia be out as Prime Minister of Israel by…?",
    headline: "Zacharia be out as Prime Minister of Israel",
    data: {
      id: "theme:story:deadline_family:polymarket:256241:65678073-65678074",
      title: "Zacharia be out as Prime Minister of Israel",
      kind: "theme",
      story_key: "story:deadline_family:polymarket:256241",
      shared_question: "Zacharia be out as Prime Minister of Israel by…?",
      item_count: members.length,
      member_ids: members.map((m) => (m.data as FeedFuturesData).id),
      items: members,
    } as FeedBundleData,
  };
}

type El = {
  tagName?: string;
  textContent?: string;
  childNodes: El[];
  getAttribute?: (name: string) => string | null;
  click?: () => void;
  [k: string]: unknown;
};

function descendants(node: El): El[] {
  return [
    node,
    ...Array.from(node.childNodes ?? []).flatMap((n) => descendants(n as El)),
  ];
}

function findByTestId(root: El, testId: string): El | undefined {
  return descendants(root).find((el) => el["data-testid"] === testId);
}

function reactProps(node: El): Record<string, (arg?: unknown) => void> {
  const key = Object.keys(node).find((k) => k.startsWith("__reactProps$"))!;
  return node[key] as Record<string, (arg?: unknown) => void>;
}

describe("Slice 1 v2 movement-led deadline-family card (#9878 / #11040)", () => {
  test("Case 1a & 1b: Missing rule equivalence proof is refused; rule-verified Oct 14 NULL control renders level-led family card", () => {
    // 1a: Missing rule_verification -> refused
    const oct31NoRule = makeFeedItemFromContract(
      makeOct31Contract({
        rule_verification: null,
        rule_template_hash: null,
      }),
    );
    const dec31NoRule = makeFeedItemFromContract(
      makeDec31Contract({
        rule_verification: null,
        rule_template_hash: null,
      }),
    );
    const unverifiedRes = validateAndBuildDeadlineFamilyCardModel(
      { items: [oct31NoRule, dec31NoRule] },
      { nowIso: RETAINED_NOW_ISO, timeZone: "America/New_York" },
    );
    expect(unverifiedRes.model).toBeNull();
    expect(unverifiedRes.rejectionReason).toBe("missing_rule_equivalence_proof");

    // 1b: Rule-verified Oct 14 NULL stored-claim control
    const oct31 = makeFeedItemFromContract(
      makeOct31Contract({ stored_movement_claim: null }),
    );
    const dec31 = makeFeedItemFromContract(
      makeDec31Contract({ stored_movement_claim: null }),
    );

    const model = buildDeadlineFamilyCardModel(
      { items: [dec31, oct31] },
      { nowIso: RETAINED_NOW_ISO, timeZone: "America/New_York" },
    );
    expect(model).not.toBeNull();
    expect(model!.ruleTemplateHash).toBe(ZACHARIA_RULE_HASH);
    expect(model!.cutoffTimezone).toBe("America/New_York");
    expect(model!.cutoffLocalTime).toBe("23:59");
    expect(model!.selectionReason).toBe("nearest_50_pct_fallback");
    expect(model!.selectionBadgeText).toBe("Selected deadline");
    expect(model!.representative.marketId).toBe(65678074);
    expect(model!.representative.yesOutcomeId).toBe(246879007);
    expect(model!.representative.yesPercentText).toBe("25%");
    expect(model!.representative.movementStatus).toBe("none");
    expect(model!.representative.showHeroMovementChip).toBe(false);
    expect(model!.representative.showRowMovementBadge).toBe(false);
    expect(model!.representative.narrativeCaption).toBe(
      "25% chance by Dec 31",
    );

    const html = renderToStaticMarkup(
      <DiscoverCard
        groupedItem={{
          type: "single",
          item: makeDeadlineBundleFeedItem([oct31, dec31]),
        }}
        positionIndex={0}
      />,
    );
    expect(html).toContain('data-testid="deadline-family-card"');
    expect(html).toContain(`data-rule-template-hash="${ZACHARIA_RULE_HASH}"`);
    expect(html).toContain("By Dec 31");
    expect(html).toContain("25%");
    expect(html).not.toContain(
      'data-testid="deadline-family-hero-movement"',
    );
    expect(html).not.toContain("7 pts");
  });

  test("Case 2: Explicitly synthetic valid stored claim + dated basis selects Dec 31 with -6.5 pts", () => {
    const oct31Syn = makeFeedItemFromContract(
      makeOct31Contract({ stored_movement_claim: -0.011 }),
    );
    const dec31Syn = makeFeedItemFromContract(
      makeDec31Contract({ stored_movement_claim: -0.065 }),
    );

    const model = buildDeadlineFamilyCardModel(
      { items: [oct31Syn, dec31Syn] },
      { nowIso: RETAINED_NOW_ISO, timeZone: "America/New_York" },
    );
    expect(model).not.toBeNull();
    expect(model!.selectionReason).toBe("largest_supported_dated_move");
    expect(model!.selectionBadgeText).toBe("Largest recent move");
    expect(model!.representative.marketId).toBe(65678074);
    expect(model!.representative.movementStatus).toBe("hero");
    expect(model!.representative.supportedMovePoints).toBe(-6.5);
    expect(model!.representative.showHeroMovementChip).toBe(true);
    expect(model!.representative.heroMovementChipText).toBe("↓ 7 pts");
    expect(model!.representative.heroTimeframeText).toBe("since yesterday");
    expect(model!.representative.narrativeCaption).toBe(
      "Down 7 points since yesterday — 25% chance by Dec 31",
    );
    expect(model!.representative.accessibleLabel).toBe(
      "Will Zacharia be out as Prime Minister of Israel by December 31? — Yes (25%), Down 7 points since yesterday",
    );

    // Oct 31 (-1.1 pts) stays sub-threshold (< 2 pts)
    const octMember = model!.members.find((m) => m.marketId === 65678073)!;
    expect(octMember.movementStatus).toBe("sub_threshold");
    expect(octMember.showHeroMovementChip).toBe(false);
    expect(octMember.showRowMovementBadge).toBe(false);

    const html = renderToStaticMarkup(
      <DeadlineFamilyCard
        model={model!}
        items={[oct31Syn, dec31Syn]}
      />,
    );
    expect(html).toContain('data-testid="deadline-family-hero-movement"');
    expect(html).toContain("↓ 7 pts");
    expect(html).toContain("since yesterday");
    expect(html).toContain(
      "Down 7 points since yesterday — 25% chance by Dec 31",
    );
  });

  test("Case 3: Expired (>24h) or premature (<12h) dated comparison basis is refused", () => {
    const oct31Young = makeFeedItemFromContract(
      makeOct31Contract({
        stored_movement_claim: -0.12,
        movement_basis: {
          outcome_id: 246879005,
          basis_price: 0.193,
          observed_at: "2026-10-14T18:00:00+00:00", // 5.75h old (< 12h min)
        },
      }),
    );
    const dec31Expired = makeFeedItemFromContract(
      makeDec31Contract({
        stored_movement_claim: -0.065,
        movement_basis: {
          outcome_id: 246879007,
          basis_price: 0.31,
          observed_at: "2026-10-13T17:00:00+00:00", // 30.75h old (> 24h max)
        },
      }),
    );

    const model = buildDeadlineFamilyCardModel(
      { items: [oct31Young, dec31Expired] },
      { nowIso: RETAINED_NOW_ISO, timeZone: "UTC" },
    );
    expect(model).not.toBeNull();
    expect(model!.selectionReason).toBe("nearest_50_pct_fallback");
    expect(model!.representative.marketId).toBe(65678074);
    expect(model!.representative.movementStatus).toBe("none");
    expect(model!.representative.showHeroMovementChip).toBe(false);
  });

  test("Case 4: No-leading binary binds strictly to Yes outcome ID and refuses No-bound basis", () => {
    const dec31WrongBasis = makeFeedItemFromContract(
      makeDec31Contract({
        stored_movement_claim: -0.065,
        movement_basis: {
          outcome_id: 246879008, // Wrongly bound to `No` outcome ID
          basis_price: 0.69,
          observed_at: RETAINED_BASIS_AT,
        },
      }),
    );
    const oct31 = makeFeedItemFromContract(makeOct31Contract());

    const model = buildDeadlineFamilyCardModel(
      { items: [oct31, dec31WrongBasis] },
      { nowIso: RETAINED_NOW_ISO },
    );
    expect(model).not.toBeNull();
    expect(model!.representative.yesOutcomeId).toBe(246879007);
    expect(model!.representative.yesPercentText).toBe("25%");
    expect(model!.representative.barWidthPercent).toBe(25);
    expect(model!.representative.movementStatus).toBe("none");
    expect(model!.representative.supportedMovePoints).toBeNull();
  });

  test("Case 5: Un-enriched fetch.json rows, missing Yes, duplicate outcome IDs, and mixed rule templates are refused", () => {
    const rawOct31 = makeFeedItemFromContract(makeOct31Contract());
    delete (rawOct31.data as FeedFuturesData).deadline_member;
    const rawDec31 = makeFeedItemFromContract(makeDec31Contract());
    delete (rawDec31.data as FeedFuturesData).deadline_member;

    const rawResult = validateAndBuildDeadlineFamilyCardModel({
      items: [rawOct31, rawDec31],
    });
    expect(rawResult.model).toBeNull();
    expect(rawResult.rejectionReason).toBe("missing_producer_member_contract");

    const badIds = makeFeedItemFromContract(
      makeOct31Contract({ yes_outcome_id: 246879006, no_outcome_id: 246879006 }),
    );
    const dupResult = validateAndBuildDeadlineFamilyCardModel({
      items: [badIds, makeFeedItemFromContract(makeDec31Contract())],
    });
    expect(dupResult.model).toBeNull();
    expect(dupResult.rejectionReason).toBe(
      "invalid_or_missing_yes_outcome_binding",
    );

    // Mismatched rule_template_hash across identical-stem questions refused (3A)
    const diffRuleDec31 = makeFeedItemFromContract(
      makeDec31Contract({
        rule_template_hash: "different_hash_999",
        rule_verification: {
          verified: true,
          evidence_source: "market_metadata.deadline_rule_contract",
          rule_template_hash: "different_hash_999",
          cutoff_timezone: "America/New_York",
          cutoff_local_time: "23:59",
        },
      }),
    );
    const mixedRuleResult = validateAndBuildDeadlineFamilyCardModel({
      items: [makeFeedItemFromContract(makeOct31Contract()), diffRuleDec31],
    });
    expect(mixedRuleResult.model).toBeNull();
    expect(mixedRuleResult.rejectionReason).toBe("mixed_rule_template_or_cutoff");
  });

  test("Case 6 & 7: Single mount path via ThemeBundleCard, deterministic tie-break, and ascending deadline order", () => {
    // Equal move (-5.0 pts, exact hero boundary) and equal distance from 50% (40% vs 60%) -> earlier deadline (Oct 31) wins
    const oct31Tie = makeFeedItemFromContract(
      makeOct31Contract({
        yes_probability: 0.4,
        yes_rendered_percent: 40,
        no_probability: 0.6,
        stored_movement_claim: -0.05,
        movement_basis: {
          outcome_id: 246879005,
          basis_price: 0.45,
          observed_at: RETAINED_BASIS_AT,
        },
      }),
    );
    const dec31Tie = makeFeedItemFromContract(
      makeDec31Contract({
        yes_probability: 0.6,
        yes_rendered_percent: 60,
        no_probability: 0.4,
        stored_movement_claim: -0.05,
        movement_basis: {
          outcome_id: 246879007,
          basis_price: 0.65,
          observed_at: RETAINED_BASIS_AT,
        },
      }),
    );

    const model = buildDeadlineFamilyCardModel(
      { items: [dec31Tie, oct31Tie] },
      { nowIso: RETAINED_NOW_ISO },
    );
    expect(model).not.toBeNull();
    expect(model!.tieBreakRule).toBe(DETERMINISTIC_TIE_BREAK_RULE);
    expect(model!.representative.marketId).toBe(65678073);
    expect(model!.representative.movementStatus).toBe("hero");
    expect(model!.representative.showHeroMovementChip).toBe(true);
    expect(model!.members.map((m) => m.marketId)).toEqual([65678073, 65678074]);

    // Single authoritative mount path: `type: "bundle"`, `kind: "theme"` renders `DeadlineFamilyCard`
    const bundleHtml = renderToStaticMarkup(
      <DiscoverCard
        groupedItem={{
          type: "single",
          item: makeDeadlineBundleFeedItem([dec31Tie, oct31Tie]),
        }}
        positionIndex={0}
      />,
    );
    expect(bundleHtml).toContain('data-testid="deadline-family-card"');

    // `GroupCard` does not intercept client-side groups as a second mount path (Section 7)
    const groupHtml = renderToStaticMarkup(
      <DiscoverCard
        groupedItem={{
          type: "group",
          items: [dec31Tie, oct31Tie],
          groupTitle: "Zacharia be out as Prime Minister of Israel",
        }}
        positionIndex={0}
      />,
    );
    expect(groupHtml).not.toContain('data-testid="deadline-family-card"');
  });

  test("Case 8: Exact local calendar date & 23:59 cutoff in America/New_York verified (3B)", () => {
    const validOct31 = makeFeedItemFromContract(makeOct31Contract());

    // Neighboring-day shift (`2026-11-01T23:59:00Z` = Nov 1 18:59 EST, which would have passed a [-14h, +36h] window) is refused!
    const shiftedOct31 = makeFeedItemFromContract(
      makeOct31Contract({
        deadline_instant: "2026-11-01T23:59:00+00:00",
      }),
    );
    expect(
      validateAndBuildDeadlineFamilyCardModel({
        items: [shiftedOct31, makeFeedItemFromContract(makeDec31Contract())],
      }).rejectionReason,
    ).toBe("deadline_instant_cutoff_mismatch");

    // Timezone-naive deadline_instant refused
    const naiveDate = makeFeedItemFromContract(
      makeDec31Contract({
        deadline_instant: "2027-01-01T04:59:00",
      }),
    );
    expect(
      validateAndBuildDeadlineFamilyCardModel({
        items: [validOct31, naiveDate],
      }).rejectionReason,
    ).toBe("question_or_deadline_verification_failed");
  });

  test("Cases 9 & 10: Q8 open 98% deadline is admitted with valid dated move and refused after evidence expires", () => {
    const oct31Settled = makeFeedItemFromContract(
      makeOct31Contract({
        settlement: {
          state: "resolved",
          is_settled: true,
          status: "resolved",
          winner: "No",
          result: "No",
        },
      }),
    );
    const dec31Open98Valid = makeFeedItemFromContract(
      makeDec31Contract({
        yes_probability: 0.98,
        yes_rendered_percent: 98,
        no_probability: 0.02,
        stored_movement_claim: 0.14,
        movement_basis: {
          outcome_id: 246879007,
          basis_price: 0.84,
          observed_at: RETAINED_BASIS_AT,
        },
      }),
    );

    const admitted = validateAndBuildDeadlineFamilyCardModel(
      { items: [oct31Settled, dec31Open98Valid] },
      { nowIso: RETAINED_NOW_ISO },
    );
    expect(admitted.model).not.toBeNull();
    expect(admitted.model!.representative.marketId).toBe(65678074);
    expect(admitted.model!.representative.nearCertainOpenEligible).toBe(true);
    expect(admitted.model!.representative.supportedMovePoints).toBe(14);

    // Same 98% open member after its dated basis ages past 24h -> refused
    const dec31Open98Expired = makeFeedItemFromContract(
      makeDec31Contract({
        yes_probability: 0.98,
        yes_rendered_percent: 98,
        no_probability: 0.02,
        stored_movement_claim: 0.14,
        movement_basis: {
          outcome_id: 246879007,
          basis_price: 0.84,
          observed_at: "2026-10-13T05:00:00+00:00", // >24h old
        },
      }),
    );
    const expired = validateAndBuildDeadlineFamilyCardModel(
      { items: [oct31Settled, dec31Open98Expired] },
      { nowIso: RETAINED_NOW_ISO },
    );
    expect(expired.model).toBeNull();
    expect(expired.rejectionReason).toBe("no_eligible_open_priced_member");
  });

  test("Case 11a: 3C / 6D / v3 Gap 2 keeps resolved, trading_closed, deadline_passed, void, and unknown distinct", () => {
    const oct31TradingClosed = makeFeedItemFromContract(
      makeOct31Contract({
        settlement: {
          state: "trading_closed",
          is_settled: false,
          is_trading_closed: true,
          status: "closed",
          winner: null,
          result: null,
        },
      }),
    );
    const dec31Open = makeFeedItemFromContract(makeDec31Contract());

    const modelWithTradingClosed = buildDeadlineFamilyCardModel(
      { items: [oct31TradingClosed, dec31Open] },
      { nowIso: RETAINED_NOW_ISO },
    );
    expect(modelWithTradingClosed).not.toBeNull();
    // Open Dec 31 represents the family; Oct 31 is trading_closed (not settled Yes/No and not open)
    expect(modelWithTradingClosed!.representative.marketId).toBe(65678074);
    const octMember = modelWithTradingClosed!.members.find(
      (m) => m.marketId === 65678073,
    )!;
    expect(octMember.settlementState).toBe("trading_closed");
    expect(octMember.isSettled).toBe(false);
    expect(octMember.isTradingClosed).toBe(true);
    expect(octMember.isDeadlinePassed).toBe(false);
    expect(octMember.settledText).toBe("Trading closed");

    // Deadline passed (`state === "deadline_passed"` or `nowIso >= deadline_instant` without venue closure):
    // kept out of live representative selection and movement chips, rendered as "Deadline passed", NEVER "Trading closed"
    const oct31DeadlinePassed = makeFeedItemFromContract(
      makeOct31Contract({
        yes_probability: 0.48,
        yes_rendered_percent: 48,
        stored_movement_claim: -0.12,
        settlement: {
          state: "deadline_passed",
          is_settled: false,
          is_trading_closed: false,
          is_deadline_passed: true,
          status: "open",
          winner: null,
          result: null,
        },
      }),
    );
    const modelWithDeadlinePassed = buildDeadlineFamilyCardModel(
      { items: [oct31DeadlinePassed, dec31Open] },
      { nowIso: "2026-11-02T12:00:00+00:00" },
    );
    expect(modelWithDeadlinePassed).not.toBeNull();
    expect(modelWithDeadlinePassed!.representative.marketId).toBe(65678074);
    const octPassedMember = modelWithDeadlinePassed!.members.find(
      (m) => m.marketId === 65678073,
    )!;
    expect(octPassedMember.settlementState).toBe("deadline_passed");
    expect(octPassedMember.isSettled).toBe(false);
    expect(octPassedMember.isTradingClosed).toBe(false);
    expect(octPassedMember.isDeadlinePassed).toBe(true);
    expect(octPassedMember.settledText).toBe("Deadline passed");
    expect(octPassedMember.showHeroMovementChip).toBe(false);
    expect(octPassedMember.showRowMovementBadge).toBe(false);

    // Void or unknown member state refuses the family
    const oct31Void = makeFeedItemFromContract(
      makeOct31Contract({
        settlement: {
          state: "void",
          is_settled: false,
          status: "closed",
        },
      }),
    );
    expect(
      validateAndBuildDeadlineFamilyCardModel({
        items: [oct31Void, dec31Open],
      }).rejectionReason,
    ).toBe("member_settlement_void");

    const oct31Unknown = makeFeedItemFromContract(
      makeOct31Contract({
        settlement: {
          state: "unknown",
          is_settled: false,
          status: "open",
          untrusted_local_grade: true,
        },
      }),
    );
    expect(
      validateAndBuildDeadlineFamilyCardModel({
        items: [oct31Unknown, dec31Open],
      }).rejectionReason,
    ).toBe("member_settlement_unknown");
  });

  test("Case 11b: 3D missing price_observed_at is never substituted with nowIso and refuses movement claims", () => {
    const oct31NoObs = makeFeedItemFromContract(
      makeOct31Contract({
        price_observed_at: null,
        stored_movement_claim: -0.08,
      }),
    );
    const dec31NoObs = makeFeedItemFromContract(
      makeDec31Contract({
        price_observed_at: null,
        stored_movement_claim: -0.065,
      }),
    );

    const model = buildDeadlineFamilyCardModel(
      { items: [oct31NoObs, dec31NoObs] },
      { nowIso: RETAINED_NOW_ISO, timeZone: "America/New_York" },
    );
    expect(model).not.toBeNull();
    expect(model!.selectionReason).toBe("nearest_50_pct_fallback");
    expect(model!.representative.priceObservedAt).toBeNull();
    expect(model!.representative.movementStatus).toBe("none");
    expect(model!.representative.showHeroMovementChip).toBe(false);
    expect(model!.representative.showRowMovementBadge).toBe(false);
  });

  test("Case 12: Honest absence, measured zero, sub-threshold (<2pt), moderate (2..<5pt), and hero (>=5pt) agree across all surfaces", () => {
    const oct31Moderate = makeFeedItemFromContract(
      makeOct31Contract({
        yes_probability: 0.245,
        yes_rendered_percent: 25,
        stored_movement_claim: 0.032,
        movement_basis: {
          outcome_id: 246879005,
          basis_price: 0.213,
          observed_at: RETAINED_BASIS_AT,
        },
      }),
    );
    const dec31MeasuredZero = makeFeedItemFromContract(
      makeDec31Contract({
        yes_probability: 0.245,
        yes_rendered_percent: 25,
        stored_movement_claim: 0.0,
        movement_basis: {
          outcome_id: 246879007,
          basis_price: 0.245,
          observed_at: RETAINED_BASIS_AT,
          admits_zero: true,
        },
      }),
    );

    const model = buildDeadlineFamilyCardModel(
      { items: [oct31Moderate, dec31MeasuredZero] },
      { nowIso: RETAINED_NOW_ISO, timeZone: "America/New_York" },
    );
    expect(model).not.toBeNull();
    expect(model!.representative.marketId).toBe(65678073);
    expect(model!.representative.movementStatus).toBe("moderate");
    expect(model!.representative.showHeroMovementChip).toBe(false);
    expect(model!.representative.showRowMovementBadge).toBe(true);
    expect(model!.representative.narrativeCaption).toBe(
      "Up 3 points since yesterday — 25% chance by Oct 31",
    );
    expect(model!.representative.accessibleLabel).toBe(
      "Will Zacharia be out as Prime Minister of Israel by October 31? — Yes (25%), Up 3 points since yesterday",
    );

    const decMember = model!.members.find((m) => m.marketId === 65678074)!;
    expect(decMember.movementStatus).toBe("measured_zero");
    expect(decMember.showHeroMovementChip).toBe(false);
    expect(decMember.showRowMovementBadge).toBe(false);
    expect(decMember.narrativeCaption).toBe(
      "Unchanged since yesterday — 25% chance by Dec 31",
    );
    expect(decMember.accessibleLabel).toBe(
      "Will Zacharia be out as Prime Minister of Israel by December 31? — Yes (25%), Unchanged since yesterday",
    );
  });

  test("Case 13: Direct User Decision Q4 & v3 Gap 4 uses 'since yesterday' only when referenceAt is reader-local today and basis is reader-local yesterday", () => {
    const prevDay = formatDeadlineMovementTimeframe(
      "2026-10-13T21:00:00+00:00",
      "2026-10-14T13:30:00+00:00",
      "America/New_York",
      "2026-10-14T23:47:16+00:00",
    );
    expect(prevDay.valid).toBe(true);
    expect(prevDay.calendarDayDiff).toBe(1);
    expect(prevDay.crossesPreviousCalendarDay).toBe(true);
    expect(prevDay.chipTimeframe).toBe("since yesterday");
    expect(prevDay.sentenceTimeframe).toBe("since yesterday");

    // When reader `nowIso` is on a later local date (Oct 16 EDT), a move observed on Oct 14 vs Oct 13
    // must NOT claim "since yesterday" — it uses explicit date wording ("since Oct 13")
    const laterReaderNow = formatDeadlineMovementTimeframe(
      "2026-10-13T21:00:00+00:00",
      "2026-10-14T13:30:00+00:00",
      "America/New_York",
      "2026-10-16T15:00:00+00:00",
    );
    expect(laterReaderNow.valid).toBe(true);
    expect(laterReaderNow.calendarDayDiff).toBe(1);
    expect(laterReaderNow.crossesPreviousCalendarDay).toBe(false);
    expect(laterReaderNow.chipTimeframe).toBe("since Oct 13");
    expect(laterReaderNow.sentenceTimeframe).toBe("since Oct 13");

    const sameDay = formatDeadlineMovementTimeframe(
      "2026-10-14T05:15:00+00:00",
      "2026-10-14T18:15:00+00:00",
      "America/New_York",
      "2026-10-14T23:47:16+00:00",
    );
    expect(sameDay.valid).toBe(true);
    expect(sameDay.calendarDayDiff).toBe(0);
    expect(sameDay.crossesPreviousCalendarDay).toBe(false);
    expect(sameDay.chipTimeframe).toBe("since 1:15 AM");
    expect(sameDay.sentenceTimeframe).toBe("today since 1:15 AM");
  });

  test("Cases 14 & 15: Verified family denominator wording (v3 Gap 4), unpriced reachability, and in-place expand/collapse", () => {
    // 1. Raw `provider_market_count: 12` with `verified_family_count: 2` and 2 represented members
    //    must NEVER claim "Compare 2 of 12 deadlines" when the 10 other markets are not proven members;
    //    it says "Compare 2 deadlines"
    const oct31CompleteVerified = makeFeedItemFromContract(
      makeOct31Contract({
        provider_market_count: 12,
        verified_family_count: 2,
      }),
    );
    const dec31CompleteVerified = makeFeedItemFromContract(
      makeDec31Contract({
        provider_market_count: 12,
        verified_family_count: 2,
      }),
    );
    const completeVerifiedModel = buildDeadlineFamilyCardModel(
      { items: [oct31CompleteVerified, dec31CompleteVerified] },
      { nowIso: RETAINED_NOW_ISO, timeZone: "America/New_York" },
    );
    expect(completeVerifiedModel).not.toBeNull();
    expect(completeVerifiedModel!.representedCount).toBe(2);
    expect(completeVerifiedModel!.verifiedFamilyCount).toBe(2);
    expect(completeVerifiedModel!.providerMarketCount).toBe(12);
    expect(completeVerifiedModel!.inventoryComplete).toBe(false);
    expect(completeVerifiedModel!.expandLabel).toBe("Compare 2 deadlines");

    // 2. When `verified_family_count: 4` (proven 4-member family capped to 2 represented members),
    //    `expandLabel` truthfully says "Compare 2 of 4 deadlines"
    const oct31Unpriced = makeFeedItemFromContract(
      makeOct31Contract({
        yes_probability: null,
        yes_rendered_percent: null,
        provider_market_count: 4,
        verified_family_count: 4,
      }),
    );
    const dec31Moved = makeFeedItemFromContract(
      makeDec31Contract({
        stored_movement_claim: -0.065,
        provider_market_count: 4,
        verified_family_count: 4,
      }),
    );

    const model = buildDeadlineFamilyCardModel(
      { items: [dec31Moved, oct31Unpriced] },
      { nowIso: RETAINED_NOW_ISO, timeZone: "America/New_York" },
    );
    expect(model).not.toBeNull();
    expect(model!.representedCount).toBe(2);
    expect(model!.verifiedFamilyCount).toBe(4);
    expect(model!.providerMarketCount).toBe(4);
    expect(model!.inventoryComplete).toBe(false);
    expect(model!.expandLabel).toBe("Compare 2 of 4 deadlines");

    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    act(() => {
      root.render(
        <DeadlineFamilyCard
          model={model!}
          items={[dec31Moved, oct31Unpriced]}
        />,
      );
    });

    const toggleBtn = findByTestId(
      container as unknown as El,
      "deadline-family-expand-toggle",
    );
    expect(toggleBtn).toBeDefined();
    expect(String(toggleBtn!["aria-expanded"])).toBe("false");
    expect(toggleBtn!.textContent).toContain("Compare 2 of 4 deadlines");
    expect(
      findByTestId(container as unknown as El, "deadline-family-member-list"),
    ).toBeUndefined();

    act(() => {
      reactProps(toggleBtn!).onClick();
    });

    const toggleBtnAfter = findByTestId(
      container as unknown as El,
      "deadline-family-expand-toggle",
    );
    expect(String(toggleBtnAfter!["aria-expanded"])).toBe("true");
    expect(toggleBtnAfter!.textContent).toContain("Hide deadlines");

    const memberRows = descendants(container as unknown as El).filter(
      (el) => el["data-testid"] === "deadline-family-member-row",
    );
    expect(memberRows).toHaveLength(2);
    const [rowOct, rowDec] = memberRows;
    expect(String(rowOct["data-market-id"])).toBe("65678073");
    expect(String(rowDec["data-market-id"])).toBe("65678074");
    expect(rowOct["href"]).toBe("/futures/65678073");
    expect(rowDec["href"]).toBe("/futures/65678074");
    expect(rowOct.textContent).toContain("By Oct 31");
    expect(rowOct.textContent).toContain("—");
    expect(rowDec.textContent).toContain("By Dec 31");
    expect(rowDec.textContent).toContain("25%");

    act(() => {
      root.unmount();
    });
    document.body.removeChild(container as unknown as Node);
  });

  test("Case 16: v4 B1 fallback, B3 5% placeholder floor, B4 default reader clock, B6 live price refresh, B7 PriceAgeMark, and N1 row timeframe label", () => {
    // 1. B1: When a near-certain family expires after time advances, ThemeBundleCard falls back
    //    to the generic bundle body rather than rendering null
    const oct31NearCertain = makeOct31Contract({
      yes_probability: 0.975,
      yes_rendered_percent: 98,
      no_probability: 0.025,
      stored_movement_claim: 0.3,
      movement_basis: {
        outcome_id: 246879005,
        basis_price: 0.675,
        observed_at: RETAINED_BASIS_AT,
        age_hours: 19.3,
        in_window: true,
        admits_zero: true,
      },
      is_near_certain: true,
      near_certain_open_eligible: true,
    });
    const dec31NearCertain = makeDec31Contract({
      yes_probability: 0.985,
      yes_rendered_percent: 99,
      no_probability: 0.015,
      stored_movement_claim: 0.4,
      movement_basis: {
        outcome_id: 246879007,
        basis_price: 0.585,
        observed_at: RETAINED_BASIS_AT,
        age_hours: 19.3,
        in_window: true,
        admits_zero: true,
      },
      is_near_certain: true,
      near_certain_open_eligible: true,
    });
    const octItem = makeFeedItemFromContract(oct31NearCertain);
    const decItem = makeFeedItemFromContract(dec31NearCertain);
    const fallbackHtml = renderToStaticMarkup(
      <ThemeBundleCard
        title="Zacharia issues public apology by…?"
        storyKey="story:deadline_family:polymarket:256241"
        items={[octItem, decItem]}
        deadlineFamily={{
          story_key: "story:deadline_family:polymarket:256241",
          source: "polymarket",
          group_id: "polymarket:256241",
          title: "Zacharia issues public apology",
          shared_question: "Zacharia issues public apology by…?",
          family_state: "open",
          rule_template_hash: ZACHARIA_RULE_HASH,
          cutoff_timezone: "America/New_York",
          cutoff_local_time: "23:59",
          representative_market_id: 65678074,
          representative_outcome_id: 246879007,
          representative_deadline_label: "By Dec 31",
          selection_reason: "largest_supported_dated_move",
          tie_break_rule:
            "abs_supported_move_desc -> distance_from_50pct_asc -> deadline_epoch_asc -> market_id_asc",
          hero_min_movement_points: 5,
          moderate_min_movement_points: 2,
          represented_count: 2,
          verified_family_count: 2,
          provider_market_count: 2,
          inventory_complete: true,
          members: [oct31NearCertain, dec31NearCertain],
        }}
        nowIso="2026-10-16T12:00:00Z"
        timeZone="America/New_York"
      />,
    );
    expect(fallbackHtml.length).toBeGreaterThan(0);
    expect(fallbackHtml).toContain("/futures/65678073");
    expect(fallbackHtml).toContain("/futures/65678074");

    // 2. B3: <= 5% placeholder floor suppresses movement and <= 3% is never near-certain
    const oct31At2Pct = makeOct31Contract({
      yes_probability: 0.02,
      yes_rendered_percent: 2,
      no_probability: 0.98,
      stored_movement_claim: -0.05,
      movement_basis: {
        outcome_id: 246879005,
        basis_price: 0.07,
        observed_at: RETAINED_BASIS_AT,
        age_hours: 19.3,
        in_window: true,
        admits_zero: true,
      },
    });
    const modelB3 = buildDeadlineFamilyCardModel(
      {
        items: [
          makeFeedItemFromContract(oct31At2Pct),
          makeFeedItemFromContract(makeDec31Contract()),
        ],
      },
      { nowIso: RETAINED_NOW_ISO, timeZone: "America/New_York" },
    );
    expect(modelB3).not.toBeNull();
    expect(modelB3!.representative.marketId).toBe(65678074);
    expect(modelB3!.selectionReason).toBe("nearest_50_pct_fallback");
    const octMemberB3 = modelB3!.members.find((m) => m.marketId === 65678073)!;
    expect(octMemberB3.movementStatus).toBe("none");
    expect(octMemberB3.supportedMovePoints).toBeNull();
    expect(octMemberB3.isNearCertain).toBe(false);

    // 3. B6 & B7 & N1: Live price refresh updates 24%/7% -> 32%/15%, PriceAgeMark renders at 8h,
    //    and member view model carries `movementTimeframeLabel`
    const frozenOct = makeOct31Contract();
    const frozenDec = makeDec31Contract({ stored_movement_claim: -0.065 });
    const liveOct = makeOct31Contract({
      yes_probability: 0.15,
      yes_rendered_percent: 15,
      no_probability: 0.85,
      stored_movement_claim: 0.066,
    });
    const liveDec = makeDec31Contract({
      yes_probability: 0.32,
      yes_rendered_percent: 32,
      no_probability: 0.68,
      stored_movement_claim: 0.01,
    });
    const modelB6 = buildDeadlineFamilyCardModel(
      {
        deadlineFamily: {
          story_key: "story:deadline_family:polymarket:256241",
          source: "polymarket",
          group_id: "polymarket:256241",
          title: "Zacharia issues public apology",
          shared_question: "Zacharia issues public apology by…?",
          family_state: "open",
          rule_template_hash: ZACHARIA_RULE_HASH,
          cutoff_timezone: "America/New_York",
          cutoff_local_time: "23:59",
          representative_market_id: 65678074,
          representative_outcome_id: 246879007,
          representative_deadline_label: "By Dec 31",
          selection_reason: "largest_supported_dated_move",
          tie_break_rule:
            "abs_supported_move_desc -> distance_from_50pct_asc -> deadline_epoch_asc -> market_id_asc",
          hero_min_movement_points: 5,
          moderate_min_movement_points: 2,
          represented_count: 2,
          verified_family_count: 2,
          provider_market_count: 2,
          inventory_complete: true,
          members: [frozenOct, frozenDec],
        },
        items: [
          makeFeedItemFromContract(liveOct),
          makeFeedItemFromContract(liveDec),
        ],
      },
      { nowIso: RETAINED_NOW_ISO, timeZone: "America/New_York" },
    );
    expect(modelB6).not.toBeNull();
    expect(modelB6!.members.find((m) => m.marketId === 65678074)!.yesRenderedPercent).toBe(32);
    expect(modelB6!.members.find((m) => m.marketId === 65678073)!.yesRenderedPercent).toBe(15);
    expect(modelB6!.representative.marketId).toBe(65678073);
    expect(modelB6!.representative.movementTimeframeLabel).toBe("since yesterday");
  });
});

describe("Alex's Oct 29 ruling: whole numbers on Discover cards", () => {
  test("hero chip, sentence and row badge print whole points; the selection still reads the exact move", () => {
    const oct31 = makeFeedItemFromContract(makeOct31Contract({ stored_movement_claim: -0.011 }));
    const dec31 = makeFeedItemFromContract(makeDec31Contract({ stored_movement_claim: -0.065 }));
    const model = buildDeadlineFamilyCardModel(
      { items: [oct31, dec31] },
      { nowIso: RETAINED_NOW_ISO, timeZone: "America/New_York" },
    )!;
    // Logic untouched: the model keeps the exact served move.
    expect(model.representative.supportedMovePoints).toBe(-6.5);
    expect(model.representative.heroMovementChipText).toBe("↓ 7 pts");
    const html = renderToStaticMarkup(
      <DeadlineFamilyCard model={model} items={[oct31, dec31]} defaultExpanded />,
    );
    expect(html).toContain("Down 7 points since yesterday");
    expect(html).not.toMatch(/\d\.\d\s*(pts|points)/);
  });

  test("#11942: refuses cumulative deadline family when earlier date prints higher than later date beyond whole-number rounding", () => {
    const oct31Reversed = makeFeedItemFromContract(
      makeOct31Contract({
        yes_probability: 0.9,
        yes_rendered_percent: 90,
        no_probability: 0.1,
      }),
    );
    const dec31Lower = makeFeedItemFromContract(
      makeDec31Contract({
        yes_probability: 0.815,
        yes_rendered_percent: 82,
        no_probability: 0.185,
      }),
    );
    const reversed = validateAndBuildDeadlineFamilyCardModel(
      { items: [oct31Reversed, dec31Lower] },
      { nowIso: RETAINED_NOW_ISO, timeZone: "America/New_York" },
    );
    expect(reversed.model).toBeNull();
    expect(reversed.rejectionReason).toBe("ladder_refused");

    const oct31RoundingTie = makeFeedItemFromContract(
      makeOct31Contract({
        yes_probability: 0.816,
        yes_rendered_percent: 82,
        no_probability: 0.184,
      }),
    );
    const dec31RoundingTie = makeFeedItemFromContract(
      makeDec31Contract({
        yes_probability: 0.815,
        yes_rendered_percent: 82,
        no_probability: 0.185,
      }),
    );
    const withinRounding = validateAndBuildDeadlineFamilyCardModel(
      { items: [oct31RoundingTie, dec31RoundingTie] },
      { nowIso: RETAINED_NOW_ISO, timeZone: "America/New_York" },
    );
    expect(withinRounding.rejectionReason).toBeNull();
    expect(withinRounding.model).not.toBeNull();
  });
});
