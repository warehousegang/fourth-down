import notice from "./assets/team-logos/NOTICE.txt?url&no-inline";

export function TeamIdentityNotice() {
  return <div className="team-identity-notice">
    <p>Fourth Down is independent and is not affiliated with or endorsed by the NFL or its teams.</p>
    <a href={notice}>Team logo sources and rights</a>
  </div>;
}
