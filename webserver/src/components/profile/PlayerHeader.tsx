import { styles } from "./profileStyles";
import RenderPlayerName from "./RenderPlayerName";

interface Props {
  playerName: string;
  gameCount: number;
  onBack: () => void;
}

export function PlayerHeader({ playerName, gameCount, onBack }: Props) {
  return (
    <header style={styles.topBar}>
      <div style={styles.topBarInner}>
        <button style={styles.backBtn} onClick={onBack}>
          ← BACK
        </button>
        <div style={styles.playerHeader}>
          <div style={styles.bigAvatar}>{playerName.slice(0, 2).toUpperCase()}</div>
          <div>
            <h1 style={styles.playerTitle}>
              <RenderPlayerName name={playerName} />
            </h1>
            <p style={styles.playerSub}>{gameCount} GAMES RECORDED</p>
          </div>
        </div>
        <div />
      </div>
    </header>
  );
}
