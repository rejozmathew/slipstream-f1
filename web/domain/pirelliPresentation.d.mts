import type { DriverPublishedStrategy, PitEvent, PublishedStrategyBaseline, PublishedStrategyOption } from "./protocol";

export const NO_SPECIFIC_PIRELLI_STRATEGY: string;
export function compoundCode(compound: string | null | undefined): string;
export function nominationSummary(selection: PublishedStrategyBaseline["compoundSelection"]): string | null;
export function prioritizedPirelliContextFacts(facts?: PublishedStrategyBaseline["contextFacts"], limit?: number): PublishedStrategyBaseline["contextFacts"];
export function optionPathText(option: PublishedStrategyOption): string;
export function optionOrderNote(option: PublishedStrategyOption): string | null;
export function optionWindowText(option: PublishedStrategyOption): string;
export function optionDeltaText(option: PublishedStrategyOption): string | null;
export function relevantPublishedOptions(baseline: PublishedStrategyBaseline | null | undefined, driver: DriverPublishedStrategy | undefined): PublishedStrategyOption[];
export function driverStrategyRelationship(baseline: PublishedStrategyBaseline | null | undefined, driver: DriverPublishedStrategy | undefined): string | null;
export function driverPublishedRouteRows(baseline: PublishedStrategyBaseline | null | undefined, driver: DriverPublishedStrategy | undefined, pitEvents?: PitEvent[]): Array<{
  id: string;
  rank: PublishedStrategyOption["rank"];
  route: string;
  orderNote: string | null;
  windows: Array<{ stopIndex: number; range: string; state: string | null }>;
}>;
export function driverPublishedRoutesText(baseline: PublishedStrategyBaseline | null | undefined, driver: DriverPublishedStrategy | undefined): string;
export function driverPublishedWindowsText(baseline: PublishedStrategyBaseline | null | undefined, driver: DriverPublishedStrategy | undefined, final?: boolean, pitEvents?: PitEvent[]): string;
