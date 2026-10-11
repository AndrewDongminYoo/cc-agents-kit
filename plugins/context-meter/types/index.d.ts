export type ContextReading = {
  /** The turn whose last request produced this reading. */
  turnId: string;
  /** The context fill in tokens: measured, or estimated when `isEstimated`. */
  tokens: number;
  /**
   * A fill the last iteration certainly reached: `tokens` when measured; when
   * estimated, the larger of the iterations' average and the previous floor.
   */
  floorTokens: number;
  /** The model's context window, in tokens. */
  window: number;
  /** `tokens` over `window`, whole percent. */
  percent: number;
  /** What the status line read at the same moment, or null when it had none. */
  harnessPercent: number | null;
  /** The request's own input total, as the API reported it. */
  summedTokens: number;
  /**
   * True when the request ran a server tool (the advisor): its usage sums the
   * message iterations around the call, and `tokens` is an upper bound on the
   * last iteration.
   */
  isEstimated: boolean;
};

declare module "claude-code" {
  interface PluginState {
    "context-meter": {
      reading: ContextReading | null;
      isNudged: boolean;
      isHidden: boolean;
    };
  }
}
