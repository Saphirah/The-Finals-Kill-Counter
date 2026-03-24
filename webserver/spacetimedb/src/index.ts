import { schema, table, t } from "spacetimedb/server";

type NamedPlayer = { name: string };

// FNV-1a 64-bit deterministic hash — used to generate stable IDs from content
// so that concurrent submissions of the same data produce the same key and the
// second insert is silently swallowed rather than racing to a conflict.
function deterministicId(key: string): bigint {
  let hash = 14695981039346656037n;
  for (let i = 0; i < key.length; i++) {
    hash ^= BigInt(key.charCodeAt(i));
    hash = (hash * 1099511628211n) & 0xffffffffffffffffn;
  }
  // Avoid 0n — reserved as an "unset" placeholder in several places
  return hash === 0n ? 1n : hash;
}

const Player = table(
  { name: "player", public: true },
  {
    name: t.string().primaryKey(),
  },
);

const winTypes = {
  win: t.unit(),
  loss: t.unit(),
  undefined: t.unit(),
};
const winType = t.enum("WinEnum", winTypes).default({ tag: "undefined" });
const MatchEntry = table(
  {
    name: "match_entry",
    public: true,
    indexes: [
      {
        accessor: "match_entry_player_name",
        algorithm: "btree",
        columns: ["playerName"],
      },
    ],
  },
  {
    id: t.u64().primaryKey(),
    playerName: t.string(),
    detectionTime: t.string(),
    map: t.string().optional(),
    similarityScore: t.f32(),
    combatScore: t.i32().optional(),
    objectiveScore: t.i32().optional(),
    supportScore: t.i32().optional(),
    eliminations: t.i32().optional(),
    assists: t.i32().optional(),
    deaths: t.i32().optional(),
    revives: t.i32().optional(),
    objectives: t.i32().optional(),
    win: winType,
  },
);

const MatchPlayer = table(
  {
    name: "match_player",
    public: true,
    indexes: [
      {
        accessor: "match_player_match_id",
        algorithm: "btree",
        columns: ["matchId"],
      },
    ],
  },
  {
    id: t.u64().primaryKey(),
    matchId: t.u64(),
    name: t.string(),
    friendly: t.bool(),
  },
);

const LiveState = table(
  { name: "live_state", public: true },
  {
    id: t.u64().primaryKey(),
    playerName: t.string(),
    map: t.string(),
    friendlyPlayers: t.string(),
    enemyPlayers: t.string(),
  },
);

const spacetimedb = schema({
  player: Player,
  matchEntry: MatchEntry,
  matchPlayer: MatchPlayer,
  liveState: LiveState,
});
export default spacetimedb;

export const submit_match = spacetimedb.reducer(
  {
    playerName: t.string(),
    detectionTime: t.string(),
    // "" means unknown map; -1 means stat was not captured.
    // Using plain types avoids the Option sum-type encoding issue over HTTP JSON.
    map: t.string(),
    win: t.bool(),
    similarityScore: t.f32(),
    combatScore: t.i32(),
    objectiveScore: t.i32(),
    supportScore: t.i32(),
    eliminations: t.i32(),
    assists: t.i32(),
    deaths: t.i32(),
    revives: t.i32(),
    objectives: t.i32(),
    friendlyPlayers: t.string(),
    enemyPlayers: t.string(),
  },
  (ctx, args) => {
    // Derive a stable, deterministic ID from the natural key (player + time).
    // Two concurrent submissions of the same data will compute the same ID, so
    // whichever reducer wins the race inserts successfully and the other's
    // try-catch swallows the duplicate-key error — fully idempotent.
    const matchEntryId = deterministicId(args.playerName + ":" + args.detectionTime);

    try {
      ctx.db.player.insert({ name: args.playerName });
    } catch {
      // Player already exists — harmless.
    }

    const opt = (v: number) => (v >= 0 ? v : undefined);
    try {
      ctx.db.matchEntry.insert({
        id: matchEntryId,
        playerName: args.playerName,
        detectionTime: args.detectionTime,
        map: args.map || undefined,
        win: args.win ? { tag: "win" } : { tag: "loss" },
        similarityScore: args.similarityScore,
        combatScore: opt(args.combatScore),
        objectiveScore: opt(args.objectiveScore),
        supportScore: opt(args.supportScore),
        eliminations: opt(args.eliminations),
        assists: opt(args.assists),
        deaths: opt(args.deaths),
        revives: opt(args.revives),
        objectives: opt(args.objectives),
      });
    } catch {
      // Duplicate match entry — another concurrent submission already inserted it.
      return;
    }

    // Insert friendly and enemy players into the MatchPlayer table.
    // IDs are derived from (matchId + playerName + side) so concurrent duplicate
    // submissions for the same match produce the same keys and are silently ignored.
    const insertPlayers = (json: string, friendly: boolean) => {
      let players: NamedPlayer[] = [];
      try {
        players = JSON.parse(json) as NamedPlayer[];
      } catch {
        return;
      }
      for (const p of players) {
        if (p && typeof p.name === "string") {
          const playerId = deterministicId(matchEntryId.toString() + ":" + p.name + ":" + (friendly ? "1" : "0"));
          try {
            ctx.db.matchPlayer.insert({
              id: playerId,
              matchId: matchEntryId,
              name: p.name,
              friendly,
            });
          } catch {
            // Duplicate match-player row — ignore.
          }
        }
      }
    };
    insertPlayers(args.friendlyPlayers, true);
    insertPlayers(args.enemyPlayers, false);
  },
);

export const delete_match = spacetimedb.reducer({ id: t.u64() }, (ctx, { id }) => {
  const existing = ctx.db.matchEntry.id.find(id);
  if (!existing) return;
  ctx.db.matchEntry.id.delete(id);
  // Delete all associated MatchPlayer rows.
  for (const mp of ctx.db.matchPlayer.match_player_match_id.filter(id)) {
    ctx.db.matchPlayer.id.delete(mp.id);
  }
});

export const update_match = spacetimedb.reducer(
  {
    id: t.u64(),
    map: t.string(),
    win: t.bool(),
    combatScore: t.i32(),
    objectiveScore: t.i32(),
    supportScore: t.i32(),
    eliminations: t.i32(),
    assists: t.i32(),
    deaths: t.i32(),
    revives: t.i32(),
    objectives: t.i32(),
  },
  (ctx, args) => {
    const existing = ctx.db.matchEntry.id.find(args.id);
    if (!existing) return;
    const opt = (v: number) => (v >= 0 ? v : undefined);
    ctx.db.matchEntry.id.update({
      ...existing,
      map: args.map || undefined,
      win: args.win ? { tag: "win" } : { tag: "loss" },
      combatScore: opt(args.combatScore),
      objectiveScore: opt(args.objectiveScore),
      supportScore: opt(args.supportScore),
      eliminations: opt(args.eliminations),
      assists: opt(args.assists),
      deaths: opt(args.deaths),
      revives: opt(args.revives),
      objectives: opt(args.objectives),
    });
  },
);

export const update_live_state = spacetimedb.reducer(
  {
    playerName: t.string(),
    map: t.string(),
    friendlyPlayers: t.string(),
    enemyPlayers: t.string(),
  },
  (ctx, args) => {
    // Single-row upsert: delete existing row (id=1) then re-insert.
    const existing = ctx.db.liveState.id.find(1n);
    if (existing) {
      ctx.db.liveState.id.delete(1n);
    }
    ctx.db.liveState.insert({
      id: 1n,
      playerName: args.playerName,
      map: args.map,
      friendlyPlayers: args.friendlyPlayers,
      enemyPlayers: args.enemyPlayers,
    });
  },
);

export const clear_live_state = spacetimedb.reducer({}, (ctx) => {
  const existing = ctx.db.liveState.id.find(1n);
  if (existing) {
    ctx.db.liveState.id.delete(1n);
  }
});
