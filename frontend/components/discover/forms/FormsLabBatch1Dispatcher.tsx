"use client";

import React from "react";
import { BubbleAndCutCard } from "./BubbleAndCutCard";
import { CalendarStripCard } from "./CalendarStripCard";
import { CastingSheetCard } from "./CastingSheetCard";
import { FallbackRowsView, FormsLabCardFrame } from "./FormsLabShell";
import { GridOfCellsCard } from "./GridOfCellsCard";
import { OneAxisCard } from "./OneAxisCard";
import type { FormsLabCardEnvelope } from "./types_forms_lab_13551";

const VARIANT_RENDERERS: Record<
  FormsLabCardEnvelope["form_variant"],
  React.ComponentType<{ card: FormsLabCardEnvelope }>
> = {
  places_grid: GridOfCellsCard,
  scoreboard_grid: GridOfCellsCard,
  shared_scale: OneAxisCard,
  deadline_race: OneAxisCard,
  the_climb: OneAxisCard,
  calendar_strip: CalendarStripCard,
  casting_sheet: CastingSheetCard,
  bubble_line: BubbleAndCutCard,
  the_cut: BubbleAndCutCard,
};

export function FormsLabBatch1Card({ card }: { card: FormsLabCardEnvelope }) {
  const Renderer = VARIANT_RENDERERS[card.form_variant];
  if (!Renderer) {
    return (
      <FormsLabCardFrame card={card}>
        <FallbackRowsView card={card} />
      </FormsLabCardFrame>
    );
  }
  return <Renderer card={card} />;
}
