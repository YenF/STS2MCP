# STS2 MCP — AI Gameplay Guide

## MCP Tool Calling Tips

### State Polling
- After `combat_end_turn`, the state may show `is_play_phase: false` or `turn: enemy`. Call `get_game_state` again to advance to the next player turn.
- Sometimes you need to call `get_game_state` twice — once to see enemy turn results, once to see your new hand.
- Use `format: "json"` during combat for structured data; `format: "markdown"` for map/event overview.

### Card Index Shifting
- **CRITICAL**: Playing a card removes it from hand and shifts all indices. Play cards from RIGHT to LEFT (highest index first) to keep lower indices stable, or re-check state between plays.
- When targeting, always provide `target` for single-target cards. Entity IDs are UPPER_SNAKE_CASE with a `_0` suffix (e.g. `KIN_PRIEST_0`).

### Event & Reward Flow
- **Events**: Use `choose_event_option` with `index` (integer). If ancient event dialogue is active, use `advance_dialogue`.
- **Rest sites (Campfire)**: Use `choose_rest_option` with `index`, then use `proceed`.
- **Rewards screen**: You MUST claim Gold, Relics, and Potions first using `claim_reward`. 
- **Opening Card Rewards**: To see or skip card choices, you MUST first select the card reward item on the rewards screen using `claim_reward`. This transitions the game state to the `CARD_REWARD` screen.
- **Card Selection screen**: Once on the `CARD_REWARD` screen, look at the cards. Choose a card using `select_card_reward` with `card_index`, or choose `skip_card_reward` to skip if none fit your deck.
- **Proceeding**: Only select `proceed` once all valuable rewards (Gold, Relics, Potions, Cards) have been resolved.

### Reward Collection Non-Negotiables
- **GOLD AND RELICS**: Gold and Relics must always be claimed. Never leave them unclaimed.
- **NEVER SKIP CARDS EARLY**: Do NOT attempt to skip card rewards directly from the `REWARDS` screen (it will fail). You MUST open the card reward first, view the options, and only then choose to select or skip them.
- **NEVER PROCEED EARLY**: Selecting `proceed` permanently closes the reward screen and discards any unclaimed items. Claim all non-card items first, open the card reward screen, make your card decision, and only then click `proceed`.

---

## General Strategy

### Core Principles
1. **HP is a resource, not a score.** Take calculated damage to deal more. Don't waste energy on block when enemies aren't attacking.
2. **Deck quality > deck size.** Skip card rewards if nothing synergizes. A lean deck draws key cards more often.
3. **Front-load damage.** Killing enemies faster means less total damage taken.
4. **Read intents carefully.** Sleep/Buff = go all-out offense. Attack = balance block and damage. Debuff = usually no damage, offense turn.

### Combat Sequencing (General)
1. Play 0-cost utility/setup cards first.
2. Play skills before attacks when possible — many mechanics reward this order (e.g. Slow debuff on enemies stacks per card played).
3. Play biggest attacks last to benefit from accumulated buffs/debuffs.
4. Check enemy HP — if you can kill this turn, skip blocking entirely.

### Map Pathing
- **Elites** give relics — fight them when healthy (>70% HP).
- **Rest before Boss** — heal if below 80% HP. Boss fights are long and punishing.
- **Unknown nodes** are safer than Elites. Good at medium HP.
- **Shops** — visit with 100+ gold.
- **Deck quality matters more than quantity** — don't add cards just because they're offered.

### Boss Fights
- **Kill the leader, not the minions.** Enemies with "Minion" power flee when their leader dies.
- Use potions aggressively in boss fights — they don't carry between acts.
- Boss fights are wars of attrition. The longer they go, the more enemies scale with Strength buffs.

### Potion Usage
- Don't hoard potions. Dying with full potions is the worst outcome.
- Use permanent-value potions (Fruit Juice = +5 Max HP) early in any combat.
- Use buff potions (Flex Potion) on turns with multiple attacks.

### Common Mistakes
- Blocking when enemies are sleeping/buffing — waste of energy.
- Not checking card indices after playing — indices shift left.
- Taking too long to kill bosses — enemies scale every turn.
- Adding mediocre cards that dilute the deck before boss fights.
