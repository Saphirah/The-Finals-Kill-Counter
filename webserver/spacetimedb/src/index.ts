import { schema, table, t } from "spacetimedb/server";

type NamedPlayer = { name: string };

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
    id: t.u64().primaryKey().autoInc(),
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
    id: t.u64().primaryKey().autoInc(),
    matchId: t.u64(),
    name: t.string(),
    friendly: t.bool(),
  },
);

const spacetimedb = schema({
  player: Player,
  matchEntry: MatchEntry,
  matchPlayer: MatchPlayer,
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
    // Reject duplicate: same player + detectionTime already in the table.
    for (const entry of ctx.db.matchEntry.match_entry_player_name.filter(args.playerName)) {
      if (entry.detectionTime === args.detectionTime) {
        // Silently return — duplicate, no insert.
        return;
      }
    }

    if (!ctx.db.player.name.find(args.playerName)) {
      ctx.db.player.insert({ name: args.playerName });
    }
    const opt = (v: number) => (v >= 0 ? v : undefined);
    ctx.db.matchEntry.insert({
      id: 0n,
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

    // Find the newly inserted match to get its auto-generated id.
    let matchId = 0n;
    for (const entry of ctx.db.matchEntry.match_entry_player_name.filter(args.playerName)) {
      if (entry.detectionTime === args.detectionTime) {
        matchId = entry.id;
        break;
      }
    }

    // Insert friendly and enemy players into the MatchPlayer table.
    const insertPlayers = (json: string, friendly: boolean) => {
      let players: NamedPlayer[] = [];
      try {
        players = JSON.parse(json) as NamedPlayer[];
      } catch {
        return;
      }
      for (const p of players) {
        if (p && typeof p.name === "string") {
          ctx.db.matchPlayer.insert({
            id: 0n,
            matchId,
            name: p.name,
            friendly,
          });
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
