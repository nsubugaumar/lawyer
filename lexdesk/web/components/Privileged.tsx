import { Icon } from "./Icon";

/** Shown where privileged file notes would be, to people outside the matter team. */
export function PrivilegedNotice() {
  return (
    <div className="notice" style={{ margin: 16 }}>
      <Icon name="lock" />
      <span>
        File notes record what the lawyers and the client discussed, and the strategy. They are privileged, so only the lawyers on this
        matter's team can read them. A partner who needs them can be added to the team.
      </span>
    </div>
  );
}
