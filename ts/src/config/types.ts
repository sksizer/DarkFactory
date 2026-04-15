/**
 * Typed configuration matching .darkfactory/config.toml structure.
 */

export interface QualityCheck {
  readonly name: string;
  /** Commands to run — all must pass. Single string or array. */
  readonly cmds: readonly string[];
}

export interface CodeConfig {
  readonly dev?: string;
  readonly quality: Readonly<Record<string, QualityCheck>>;
}

export interface ConfigV1 {
  readonly code: CodeConfig;
  readonly workflow?: {
    readonly directories?: readonly string[];
  };
}

export interface DarkFactoryConfig {
  readonly v1: ConfigV1;
}
