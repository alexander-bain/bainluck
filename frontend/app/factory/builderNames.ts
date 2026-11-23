import { useEffect, useState } from "react";
import { builderLanes, type Builder, type NamedBuilder } from "./types";

export type { NamedBuilder } from "./types";
export type CrewIdentity = NamedBuilder | "Fable";
export type NameableBuilder = Exclude<CrewIdentity, "Factory">;
export type FactoryNames = Record<Builder | "Fable", string>;
type CustomNames = Partial<Record<NameableBuilder, string>>;

export const builders = builderLanes;
export const crewIdentities = [...builders, "Fable"] as const;
export const nameableBuilders: readonly NameableBuilder[] = crewIdentities.filter(key => key !== "Factory");

export const defaultNames: FactoryNames = {
  S: "Speed",
  B: "Builder B",
  C: "Builder C",
  D: "Atlas",
  E: "Builder E",
  F: "Builder F",
  W: "Wee-Bey",
  Factory: "Factory",
  Fable: "Fable",
  Other: "Earlier work",
};

export const BUILDER_NAME_LIMIT = 24;
const STORAGE_KEY = "factory-builder-names-v1";

function limitName(value: string) {
  return [...value].slice(0, BUILDER_NAME_LIMIT).join("").replace(/\s+/g, " ");
}

function readNames(): CustomNames {
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    if (stored === null || typeof stored !== "object") return {};
    const entries = stored as Record<string, unknown>;
    const custom: CustomNames = {};
    for (const key of nameableBuilders) {
      const value = entries[key];
      if (typeof value === "string") custom[key] = limitName(value);
    }
    return custom;
  } catch {
    return {};
  }
}

export function holdAuthorName(author: string, names: FactoryNames) {
  if (author === "Alex") return "Repository owner";
  if (author === "Apple") return names.F;
  const builder = nameableBuilders.find(key => defaultNames[key] === author);
  return builder ? names[builder] : author;
}

export function useBuilderNames() {
  const [custom, setCustom] = useState<CustomNames>({});

  useEffect(() => {
    setCustom(readNames());
    function onStorage(event: StorageEvent) {
      if (event.key === STORAGE_KEY || event.key === null) setCustom(readNames());
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  function changeName(key: NameableBuilder, value: string) {
    const next = { ...custom, [key]: limitName(value) };
    setCustom(next);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // Names can still be used during this visit.
    }
  }

  function resetNames() {
    setCustom({});
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // The names still reset in the open page.
    }
  }

  const names = { ...defaultNames };
  for (const key of nameableBuilders) {
    names[key] = custom[key]?.trim() || defaultNames[key];
  }

  return { names, custom, changeName, resetNames };
}
