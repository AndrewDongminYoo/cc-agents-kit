/** Absolute paths of files the agent touched or named, newest first. */
export type RecentFiles = string[];

declare module "claude-code" {
  interface PluginState {
    "quick-look": {
      recent: RecentFiles;
    };
  }
}
