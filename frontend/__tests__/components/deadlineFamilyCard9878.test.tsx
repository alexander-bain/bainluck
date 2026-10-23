/**
 * Discriminating frontend tests for Slice 1 movement-led deadline-family card (#9878 / #11040).
 *
 * Covers all Section 4, 5, 6, 7, and 8 requirements:
 * - Case 1: Actual retained Oct 14 NULL stored-claim control (markets 65678073 & 65678074).
 * - Case 2: Explicitly synthetic valid stored claim + outcome-bound dated comparison basis.
 * - Case 3: Expired (>24h) or premature (<12h) dated basis refused; fallback to nearest 50%.
 * - Case 4: No-leading binary outcomes — exact Yes outcome ID supplies every value.
 * - Case 5: Raw un-enriched `fetch.json` rows, missing Yes, duplicate IDs, and negative wording refused.
 * - Case 6: One family consumes one feed seat across both `type: "bundle"` and `grouped` shapes.
 * - Case 7: Deterministic tie-breaks and ascending `deadline_instant` ordering.
 * - Case 8: Mixed predicates, exclusive date buckets, mention-only, and timezone-naive/contradictory dates refused.
 * - Case 9 & 10: Q8 local 97%+ open-mover exception admitted while evidence is in-window and refused after expiry.
 * - Case 11: 6D authoritative venue settlement overrides lagging local `status="open"`; extreme prices alone do not settle.
 * - Case 12: 6E honest absence, measured zero, sub-threshold (<2pt), moderate (2..<5pt), and hero (>=5pt) agreement.
 * - Case 13: Direct User Decision Q4 reader-local calendar-day comparison wording ("since yesterday" vs same-day clock).
 * - Case 14: 6F represented count vs provider inventory completeness and unpriced member reachability.
 * - Case 15: Q2 in-place expand/collapse and preserved `/futures/{id}` member destinations.
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
import {
  DETERMINISTIC_TIE_BREAK_RULE,
  buildDeadlineFamilyCardModel,
  formatDeadlineMovementTimeframe,
  validateAndBuildDeadlineFamilyCardModel,
} from "../../lib/discover/deadlineFamilyCard";

const RETAINED_NOW_ISO = "2026-10-14T13:34:00+00:00";
const RETAINED_BASIS_AT = "2026-10-13T16:10:00+00:00";

function makeOct31Contract(
  overrides: Partial<FeedDeadlineMemberContract> = {},
): FeedDeadlineMemberContract {
  return {
    market_id: 65678073,
    name: "Will Zacharia be out as Prime Minister of Israel by October 31?",
    source: "polymarket",
    external_id:
      "0x42cb81f5eb2fe892f7b1851a8ca9c54f513328b8bc55ff07825a1df5ebdf5f6d",
    group_id: "polymarket:1183118",
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
    deadline_instant: "2026-10-31T23:59:00+00:00",
    deadline_epoch: 1793491140,
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
    price_observed_at: "2026-10-14T13:20:00+00:00",
    stored_movement_claim: null,
    movement_basis: {
      outcome_id: 246879005,
      basis_price: 0.084,
      observed_at: RETAINED_BASIS_AT,
      age_hours: 21.4,
      in_window: true,
    },
    movement_status: "no_stored_claim",
    supported_move: null,
    supported_move_points: null,
    show_hero_movement_chip: false,
    show_row_movement_badge: false,
    settlement: {
      is_settled: false,
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
    group_id: "polymarket:1183118",
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
    deadline_instant: "2026-12-31T23:59:00+00:00",
    deadline_epoch: 1798761540,
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
    price_observed_at: "2026-10-14T13:20:00+00:00",
    stored_movement_claim: null,
    movement_basis: {
      outcome_id: 246879007,
      basis_price: 0.31,
      observed_at: RETAINED_BASIS_AT,
      age_hours: 21.4,
      in_window: true,
    },
    movement_status: "no_stored_claim",
    supported_move: null,
    supported_move_points: null,
    show_hero_movement_chip: false,
    show_row_movement_badge: false,
    settlement: {
      is_settled: false,
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
      id: "theme:story:deadline_family:polymarket:1183118:65678073-65678074",
      title: "Zacharia be out as Prime Minister of Israel",
      kind: "theme",
      story_key: "story:deadline_family:polymarket:1183118",
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

describe("Slice 1 movement-led deadline-family card (#9878 / #11040)", () => {
  test("Case 1: Retained Oct 14 NULL stored claims render one family card with zero fabricated movement", () => {
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
    expect(html).toContain("By Dec 31");
    expect(html).toContain("25%");
    expect(html).not.toContain(
      'data-testid="deadline-family-hero-movement"',
    );
    expect(html).not.toContain("6.5 pts");
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
    expect(model!.selectionBadgeText).toBe("Largest 24h move");
    expect(model!.representative.marketId).toBe(65678074);
    expect(model!.representative.movementStatus).toBe("hero");
    expect(model!.representative.supportedMovePoints).toBe(-6.5);
    expect(model!.representative.showHeroMovementChip).toBe(true);
    expect(model!.representative.heroMovementChipText).toBe("↓ 6.5 pts");
    expect(model!.representative.heroTimeframeText).toBe("since yesterday");
    expect(model!.representative.narrativeCaption).toBe(
      "Down 6.5 points since yesterday — 25% chance by Dec 31",
    );
    expect(model!.representative.accessibleLabel).toBe(
      "Will Zacharia be out as Prime Minister of Israel by December 31? — Yes (25%), Down 6.5 points since yesterday",
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
    expect(html).toContain("↓ 6.5 pts");
    expect(html).toContain("since yesterday");
    expect(html).toContain(
      "Down 6.5 points since yesterday — 25% chance by Dec 31",
    );
  });

  test("Case 3: Expired (>24h) or premature (<12h) dated comparison basis is refused", () => {
    const oct31Young = makeFeedItemFromContract(
      makeOct31Contract({
        stored_movement_claim: -0.12,
        movement_basis: {
          outcome_id: 246879005,
          basis_price: 0.193,
          observed_at: "2026-10-14T08:00:00+00:00", // 5.5h old (< 12h min)
        },
      }),
    );
    const dec31Expired = makeFeedItemFromContract(
      makeDec31Contract({
        stored_movement_claim: -0.065,
        movement_basis: {
          outcome_id: 246879007,
          basis_price: 0.31,
          observed_at: "2026-10-13T07:00:00+00:00", // 30.5h old (> 24h max)
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

  test("Case 5: Un-enriched fetch.json rows, missing Yes, duplicate outcome IDs, and negative wording are refused", () => {
    // Raw fetch.json item with no producer `deadline_member` contract
    const rawOct31 = makeFeedItemFromContract(makeOct31Contract());
    delete (rawOct31.data as FeedFuturesData).deadline_member;
    const rawDec31 = makeFeedItemFromContract(makeDec31Contract());
    delete (rawDec31.data as FeedFuturesData).deadline_member;

    const rawResult = validateAndBuildDeadlineFamilyCardModel({
      items: [rawOct31, rawDec31],
    });
    expect(rawResult.model).toBeNull();
    expect(rawResult.rejectionReason).toBe("missing_producer_member_contract");

    // Duplicate outcome IDs refused
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

    // Negatively worded question refused
    const negQuestion = makeFeedItemFromContract(
      makeOct31Contract({
        name: "Will Zacharia not be out as Prime Minister of Israel by October 31?",
      }),
    );
    const negResult = validateAndBuildDeadlineFamilyCardModel({
      items: [negQuestion, makeFeedItemFromContract(makeDec31Contract())],
    });
    expect(negResult.model).toBeNull();
    expect(negResult.rejectionReason).toBe(
      "question_or_deadline_verification_failed",
    );
  });

  test("Case 6 & 7: Deterministic tie-break and ascending deadline order across bundle and grouped shapes", () => {
    // Equal move (-5.0 pts) and equal distance from 50% (40% vs 60%) -> earlier deadline (Oct 31) wins
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
    expect(model!.members.map((m) => m.marketId)).toEqual([65678073, 65678074]);

    // Also renders via DiscoverCard groupedItem.type === "group"
    const groupedHtml = renderToStaticMarkup(
      <DiscoverCard
        groupedItem={{
          type: "group",
          items: [dec31Tie, oct31Tie],
          groupTitle: "Zacharia be out as Prime Minister of Israel",
        }}
        positionIndex={0}
      />,
    );
    expect(groupedHtml).toContain('data-testid="deadline-family-card"');
  });

  test("Case 8: Mixed predicates, exclusive buckets, mention-only, and timezone-naive/contradictory dates are refused", () => {
    const validOct31 = makeFeedItemFromContract(makeOct31Contract());

    const diffPred = makeFeedItemFromContract(
      makeDec31Contract({
        name: "Will Zacharia visit Washington by December 31?",
      }),
    );
    expect(
      validateAndBuildDeadlineFamilyCardModel({
        items: [validOct31, diffPred],
      }).rejectionReason,
    ).toBe("mixed_subject_or_predicate");

    const exclusiveBucket = makeFeedItemFromContract(
      makeDec31Contract({
        name: "Will Zacharia be out as Prime Minister of Israel in December?",
      }),
    );
    expect(
      validateAndBuildDeadlineFamilyCardModel({
        items: [validOct31, exclusiveBucket],
      }).rejectionReason,
    ).toBe("question_or_deadline_verification_failed");

    const naiveDate = makeFeedItemFromContract(
      makeDec31Contract({
        deadline_instant: "2026-12-31T23:59:00",
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
          observed_at: "2026-10-13T05:00:00+00:00", // 32.5h old
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

  test("Case 11: Authoritative venue settlement overrides lagging local open status and suppresses live move", () => {
    const oct31Open = makeFeedItemFromContract(makeOct31Contract());
    const dec31VenueResolved = makeFeedItemFromContract(
      makeDec31Contract({
        yes_probability: 0.98,
        yes_rendered_percent: 98,
        stored_movement_claim: 0.84,
        movement_basis: {
          outcome_id: 246879007,
          basis_price: 0.14,
          observed_at: RETAINED_BASIS_AT,
        },
        settlement: {
          is_settled: true,
          status: "resolved",
          winner: "Yes",
          result: "Yes",
          authoritative_source: "venue_metadata",
          lagging_local_status: true,
        },
      }),
    );
    // Simulate lagging local status="open" on the outer item
    (dec31VenueResolved.data as FeedFuturesData).status = "open";

    const model = buildDeadlineFamilyCardModel(
      { items: [oct31Open, dec31VenueResolved] },
      { nowIso: RETAINED_NOW_ISO },
    );
    expect(model).not.toBeNull();
    // Dec 31 is settled so open Oct 31 represents the open family
    expect(model!.representative.marketId).toBe(65678073);
    const decMember = model!.members.find((m) => m.marketId === 65678074)!;
    expect(decMember.isSettled).toBe(true);
    expect(decMember.settledText).toBe("Resolved · Yes");
    expect(decMember.laggingLocalStatus).toBe(true);
    expect(decMember.showHeroMovementChip).toBe(false);
    expect(decMember.showRowMovementBadge).toBe(false);
    expect(decMember.supportedMovePoints).toBeNull();
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
    // Oct 31 (+3.2 pts moderate move) leads over Dec 31 (measured zero)
    expect(model!.representative.marketId).toBe(65678073);
    expect(model!.representative.movementStatus).toBe("moderate");
    expect(model!.representative.showHeroMovementChip).toBe(false); // < 5 pts (Q7)
    expect(model!.representative.showRowMovementBadge).toBe(true); // >= 2 pts
    expect(model!.representative.narrativeCaption).toBe(
      "Up 3.2 points since yesterday — 25% chance by Oct 31",
    );
    expect(model!.representative.accessibleLabel).toBe(
      "Will Zacharia be out as Prime Minister of Israel by October 31? — Yes (25%), Up 3.2 points since yesterday",
    );

    // Dec 31 measured zero gets "Unchanged since yesterday"
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

  test("Case 13: Direct User Decision Q4 uses 'since yesterday' only across previous local calendar day", () => {
    const prevDay = formatDeadlineMovementTimeframe(
      "2026-10-13T21:00:00+00:00",
      "2026-10-14T13:30:00+00:00",
      "America/New_York",
    );
    expect(prevDay.valid).toBe(true);
    expect(prevDay.calendarDayDiff).toBe(1);
    expect(prevDay.chipTimeframe).toBe("since yesterday");
    expect(prevDay.sentenceTimeframe).toBe("since yesterday");

    // 13 hours apart on the SAME local calendar day in America/New_York (1:15 AM EDT -> 2:15 PM EDT)
    const sameDay = formatDeadlineMovementTimeframe(
      "2026-10-14T05:15:00+00:00",
      "2026-10-14T18:15:00+00:00",
      "America/New_York",
    );
    expect(sameDay.valid).toBe(true);
    expect(sameDay.calendarDayDiff).toBe(0);
    expect(sameDay.crossesPreviousCalendarDay).toBe(false);
    expect(sameDay.chipTimeframe).toBe("since 1:15 AM");
    expect(sameDay.sentenceTimeframe).toBe("today since 1:15 AM");
  });

  test("Cases 14 & 15: Partial inventory wording, unpriced reachability, and in-place expand/collapse with member links", () => {
    const oct31Unpriced = makeFeedItemFromContract(
      makeOct31Contract({
        yes_probability: null,
        yes_rendered_percent: null,
        provider_market_count: 4,
      }),
    );
    const dec31Moved = makeFeedItemFromContract(
      makeDec31Contract({
        stored_movement_claim: -0.065,
        provider_market_count: 4,
      }),
    );

    const model = buildDeadlineFamilyCardModel(
      { items: [dec31Moved, oct31Unpriced] },
      { nowIso: RETAINED_NOW_ISO, timeZone: "America/New_York" },
    );
    expect(model).not.toBeNull();
    expect(model!.representedCount).toBe(2);
    expect(model!.providerMarketCount).toBe(4);
    expect(model!.inventoryComplete).toBe(false);
    expect(model!.expandLabel).toBe("Compare 2 of 4 deadlines");

    // Mount interactively and verify Q2 in-place expansion
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

    // Expand in place
    act(() => {
      reactProps(toggleBtn!).onClick();
    });

    const toggleBtnAfter = findByTestId(
      container as unknown as El,
      "deadline-family-expand-toggle",
    );
    expect(String(toggleBtnAfter!["aria-expanded"])).toBe("true");
    expect(toggleBtnAfter!.textContent).toContain("Hide deadlines");

    const expandedList = findByTestId(
      container as unknown as El,
      "deadline-family-member-list",
    );
    expect(expandedList).toBeDefined();

    // Verify ascending deadline order (65678073 By Oct 31 first, 65678074 By Dec 31 second)
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
});
