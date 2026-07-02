#!/usr/bin/env python3
"""
ollama_agent.py - Slay the Spire 2 Agentic & Interactive Local Ollama Runner

This script retrieves game state from the local STS2MCP mod, sends it to a local
Ollama instance for decision-making (using strategy guides from AGENTS.md),
and automatically or interactively posts the actions back to the game.
"""

import sys
import os
import json
import argparse
import time
import httpx

# ANSI Color escapes for terminal UI
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_RED = "\033[31m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_BLUE = "\033[34m"
C_MAGENTA = "\033[35m"
C_CYAN = "\033[36m"
C_WHITE = "\033[37m"

def print_header(title):
    print(f"\n{C_BOLD}{C_MAGENTA}=== {title} ==={C_RESET}")

def print_info(msg):
    print(f"{C_CYAN}[i] {msg}{C_RESET}")

def print_warning(msg):
    print(f"{C_YELLOW}[!] {msg}{C_RESET}")

def print_error(msg):
    print(f"{C_RED}[ERROR] {msg}{C_RESET}", file=sys.stderr)

def print_success(msg):
    print(f"{C_GREEN}[✓] {msg}{C_RESET}")

class STS2Agent:
    def __init__(self, game_url, ollama_url, model, interactive):
        self.game_url = game_url.rstrip('/')
        self.ollama_url = ollama_url.rstrip('/')
        self.model = model
        self.interactive = interactive
        self.launched_interactive = interactive
        self.client = httpx.Client(timeout=180.0)
        self.strategy_guide = ""
        self.load_strategy_guide()
        self.action_history = []
        self.last_state_signature = None
        self.last_stats = None

    def load_strategy_guide(self):
        """Loads strategy rules from AGENTS.md to feed to Ollama's system prompt."""
        agents_md_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "AGENTS.md")
        if os.path.exists(agents_md_path):
            try:
                with open(agents_md_path, "r", encoding="utf-8") as f:
                    self.strategy_guide = f.read()
                print_success("Loaded strategy guide from AGENTS.md")
            except Exception as e:
                print_warning(f"Could not read AGENTS.md: {e}. Running without custom strategy.")
        else:
            print_warning("AGENTS.md not found in the workspace. Running without custom strategy.")

    def check_services(self):
        """Verifies both STS2 Game Mod and local Ollama are reachable."""
        # 1. Check Game Mod
        try:
            r = self.client.get(f"{self.game_url}/")
            if r.status_code == 200:
                print_success(f"Connected to Slay the Spire 2 Mod REST API at {self.game_url}")
            else:
                print_error(f"Game REST API returned status {r.status_code}")
                return False
        except httpx.ConnectError:
            print_error(f"Could not connect to Slay the Spire 2 Mod at {self.game_url}.\n"
                        f"Please launch Slay the Spire 2 and verify that mods are enabled in settings.")
            return False

        # 2. Check Ollama
        try:
            r = self.client.get(f"{self.ollama_url}/")
            # Ollama root endpoint responds with "Ollama is running"
            if r.status_code == 200 or "Ollama is running" in r.text:
                print_success(f"Connected to Ollama API at {self.ollama_url}")
            else:
                print_error(f"Ollama API returned status {r.status_code}")
                return False
        except httpx.ConnectError:
            print_error(f"Could not connect to Ollama at {self.ollama_url}.\n"
                        f"Please start Ollama App or run 'ollama serve' in your terminal.")
            return False

        # 3. Verify Model is downloaded
        try:
            r = self.client.get(f"{self.ollama_url}/api/tags")
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                # Check for tag match or partial match
                model_found = False
                for m in models:
                    if self.model in m or m in self.model:
                        self.model = m # set exact tag name
                        model_found = True
                        break
                if model_found:
                    print_success(f"Ollama model '{self.model}' is available.")
                else:
                    print_warning(f"Ollama model '{self.model}' was not found in local tags list.\n"
                                  f"Available models: {models}.\n"
                                  f"We will attempt to pull it automatically...")
                    self.pull_model()
            else:
                print_warning("Could not verify Ollama models tags. Continuing anyway...")
        except Exception as e:
            print_warning(f"Could not check Ollama models: {e}. Continuing...")
            
        return True

    def pull_model(self):
        """Pulls the specified model in Ollama."""
        print_info(f"Pulling Ollama model '{self.model}' (this might take a while)...")
        try:
            r = self.client.post(f"{self.ollama_url}/api/pull", json={"name": self.model}, timeout=600.0)
            if r.status_code == 200:
                print_success(f"Model '{self.model}' pulled successfully.")
            else:
                print_error(f"Failed to pull model: HTTP {r.status_code} - {r.text}")
        except Exception as e:
            print_error(f"Error pulling model: {e}")

    def pull_game_state(self, format_type):
        """Fetches the game state from the REST API."""
        r = self.client.get(f"{self.game_url}/api/v1/singleplayer", params={"format": format_type})
        r.raise_for_status()
        if format_type == "json":
            return r.json()
        return r.text

    def post_action(self, action_body):
        """Sends the action payload to the Slay the Spire 2 API."""
        print_info(f"Executing action in game: {C_BOLD}{action_body}{C_RESET}")
        r = self.client.post(f"{self.game_url}/api/v1/singleplayer", json=action_body)
        r.raise_for_status()
        res = r.json()
        if res.get("status") == "error":
            print_error(f"Mod error: {res.get('error')}")
        else:
            print_success(f"Action result: {res.get('message', 'ok')}")
        return res

    def query_ollama(self, state_markdown):
        """Asks local Ollama to choose an action based on the state and guidelines."""
        system_prompt = (
            "You are an expert Slay the Spire 2 AI agent playing the game via tool calls.\n"
            "Your task is to analyze the current game state and output the single best action to execute next.\n\n"
            "=== STRATEGY & API SPECIFICATION GUIDE ===\n"
            f"{self.strategy_guide}\n\n"
            "=== IMPORTANT ACTION OUTPUT RULES ===\n"
            "1. You must respond ONLY with a single valid JSON object representing the action.\n"
            "2. Do NOT add markdown code block formatting (like ```json). Respond with plain text JSON only.\n"
            "3. Do NOT add explanation, thinking, or introduction text. Just output the JSON.\n"
            "4. Playability: Cards in Hand have playability markers: '✓' (playable) or '✗' (unplayable due to energy or constraints). You MUST ONLY recommend playing cards marked with '✓'. Do NOT play cards marked with '✗'.\n"
            "5. Match the keys exactly as shown in the guides. For example:\n"
            "   - Combat cards (Requires target if single-target, e.g. Bash/Strike): {\"action\": \"play_card\", \"card_index\": N, \"target\": \"ENEMY_NAME_0\"}\n"
            "     (Note: You MUST provide 'target' with the exact enemy entity ID from the 'Enemies' section, e.g. \"NIBBIT_0\" or \"JAW_WORM_0\")\n"
            "   - Combat cards (No target, e.g. Defend): {\"action\": \"play_card\", \"card_index\": N}\n"
            "   - End combat turn: {\"action\": \"end_turn\"}\n"
            "   - Menu select / Game over return: {\"action\": \"menu_select\", \"option\": \"option_id\"}\n"
            "     (Note: For Game Over screen, option MUST be \"main_menu\". For Character Select screen, first select the character ID (e.g. \"IRONCLAD\") and then choose option \"confirm\" or \"embark\" to start the run)\n"
            "   - Map travel: {\"action\": \"choose_map_node\", \"index\": N}\n"
            "   - Rest site options: {\"action\": \"choose_rest_option\", \"index\": N}\n"
            "   - Claim combat rewards: {\"action\": \"claim_reward\", \"index\": N}\n"
            "   - Claim treasure relic (chest): {\"action\": \"claim_treasure_relic\", \"index\": N}\n"
            "   - Select card reward: {\"action\": \"select_card_reward\", \"card_index\": N}\n"
            "   - Skip card reward: {\"action\": \"skip_card_reward\"}\n"
            "   - Shop purchase: {\"action\": \"shop_purchase\", \"index\": N}\n"
            "   - Event option select: {\"action\": \"choose_event_option\", \"index\": N}\n"
            "   - Dialogue advance (if in dialogue): {\"action\": \"advance_dialogue\"}\n"
            "   - Grid card selection (e.g. upgrade/transform): {\"action\": \"select_card\", \"index\": N}\n"
            "   - Grid selection confirm: {\"action\": \"confirm_selection\"}\n"
            "   - Grid selection cancel: {\"action\": \"cancel_selection\"}\n"
            "   - Use potion: {\"action\": \"use_potion\", \"slot\": N, \"target\": \"ENEMY_NAME_0\"}\n"
            "   - Discard potion: {\"action\": \"discard_potion\", \"slot\": N}\n"
            "   - Proceed to next screen: {\"action\": \"proceed\"}\n\n"
            "=== STRATEGIC PLANNING RULES ===\n"
            "- Always review the \"Deck Information\" (draw pile, discard pile) and relics in the game state.\n"
            "- Plan several steps ahead: track what cards will be drawn next, count enemy damage vs your block, and preserve energy or potions for key turns.\n"
        )

        user_prompt = (
            "Here is the history of recent actions in this screen state (do NOT repeat failed actions):\n"
            f"{self.format_history()}\n\n"
            "Here is the current Slay the Spire 2 game state:\n\n"
            f"{state_markdown}\n\n"
            "Analyze the state, check enemy intents and card costs, and select your next action. Output ONLY the JSON."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,  # Keep it highly deterministic
                "num_ctx": 32768     # Prevent truncation of strategy guide and game state
            }
        }

        try:
            r = self.client.post(f"{self.ollama_url}/api/chat", json=payload)
            r.raise_for_status()
            response_json = r.json()
            content = response_json["message"]["content"].strip()
            
            # Store stats for display
            prompt_tokens = response_json.get("prompt_eval_count", 0)
            eval_tokens = response_json.get("eval_count", 0)
            eval_duration_ns = response_json.get("eval_duration", 0)
            total_duration_ns = response_json.get("total_duration", 0)
            
            eval_s = eval_duration_ns / 1e9
            total_s = total_duration_ns / 1e9
            tokens_per_sec = eval_tokens / eval_s if eval_s > 0 else 0.0
            
            self.last_stats = {
                "prompt_tokens": prompt_tokens,
                "eval_tokens": eval_tokens,
                "tokens_per_sec": tokens_per_sec,
                "total_s": total_s
            }
            
            # Clean up potential markdown formatting if the model ignored system prompts
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            
            # Parse it to confirm it's valid JSON
            action_data = json.loads(content)
            return action_data
        except Exception as e:
            print_error(f"Error communicating with or parsing Ollama: {e}")
            if 'content' in locals():
                print_error(f"Raw content returned was: {content}")
            return None

    def check_for_pause_request(self):
        """Checks if the user has pressed Enter to pause the autonomous loop."""
        import select
        try:
            rlist, _, _ = select.select([sys.stdin], [], [], 0.0)
            if rlist:
                sys.stdin.readline()  # Consume the newline
                print_header("PAUSED - Interactive Control Restored")
                self.interactive = True
                return True
        except Exception:
            pass
        return False

    def explain_suggestion(self, state_markdown, recommendation):
        """Asks Ollama to explain why it recommended a particular action."""
        system_prompt = (
            "You are an expert Slay the Spire 2 player explaining your tactical reasoning.\n"
            "Given the current game state and your recommended action, explain your choice clearly.\n"
            "Keep your explanation concise (1-3 sentences max) focusing on immediate tactical value (e.g. damage math, block requirements, or card synergy)."
        )
        
        user_prompt = (
            "Here is the game state:\n"
            f"{state_markdown}\n\n"
            f"You recommended this action: {json.dumps(recommendation)}\n\n"
            "Explain in 1-3 sentences why this is the best move."
        )
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_ctx": 32768
            }
        }
        
        try:
            r = self.client.post(f"{self.ollama_url}/api/chat", json=payload)
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
        except Exception as e:
            return f"Failed to get explanation: {e}"

    def format_history(self):
        if not self.action_history:
            return "No recent actions."
        lines = []
        for act, res in self.action_history[-6:]:
            lines.append(f"- Action: {json.dumps(act)} -> Result: {res}")
        return "\n".join(lines)

    def display_interactive_menu(self, state_json, state_markdown, ollama_suggestion):
        """Displays options to the user for interactive co-op play."""
        print_header("Interactive Panel")
        
        # Display suggestion
        if ollama_suggestion:
            print(f"{C_YELLOW}Ollama recommends:   {C_BOLD}{json.dumps(ollama_suggestion)}{C_RESET}")
            if self.last_stats:
                stats = self.last_stats
                pct = (stats['prompt_tokens'] / 32768) * 100
                print(f"{C_CYAN}[Stats] Context: {stats['prompt_tokens']:,} / 32,768 tokens ({pct:.1f}% used) | Gen: {stats['eval_tokens']} tkn ({stats['tokens_per_sec']:.1f} t/s) | Time: {stats['total_s']:.2f}s{C_RESET}")
        else:
            print(f"{C_RED}Ollama failed to generate a recommendation.{C_RESET}")
            
        print("\nChoose an option:")
        print(f"[{C_GREEN}Enter{C_RESET}] Accept Ollama's recommendation (if available)")
        print(f"[{C_GREEN}c{C_RESET}]     Continuous Play - Let the agent play automatically until you hit Enter to pause")
        print(f"[{C_GREEN}y{C_RESET}]     Why? - Ask the agent to explain the reasoning behind its recommendation")
        print(f"[{C_GREEN}r{C_RESET}]     Refresh - Fetch new state and ask Ollama again (use after manual plays)")
        print(f"[{C_YELLOW}m{C_RESET}]     Manual Mode - Pause script so you can play directly in game. Press Enter here when done.")
        print(f"[{C_CYAN}l{C_RESET}]     List state details (Print Markdown representation of state)")
        print(f"[{C_BLUE}a{C_RESET}]     Show valid actions list")
        print(f"[{C_RED}q{C_RESET}]     Quit agent runner")
        
        choice = input(f"{C_BOLD}Your choice > {C_RESET}").strip()
        
        if choice == "":
            if ollama_suggestion:
                if ollama_suggestion.get("action") == "get_game_state":
                    return "refresh", None
                return "execute_ollama", ollama_suggestion
            else:
                print_warning("No Ollama suggestion available. Choose another option.")
                return "wait", None
        elif choice.lower() == 'c':
            print_info("Continuous play activated. Let the AI run! Press [Enter] at any time to regain control.")
            self.interactive = False
            if ollama_suggestion:
                if ollama_suggestion.get("action") == "get_game_state":
                    return "refresh", None
                return "execute_ollama", ollama_suggestion
            else:
                return "refresh", None
        elif choice.lower() == 'y':
            if ollama_suggestion:
                print_info("Asking Ollama for reasoning...")
                explanation = self.explain_suggestion(state_markdown, ollama_suggestion)
                print(f"\n{C_YELLOW}Explanation:{C_RESET}\n{explanation}\n")
            else:
                print_warning("No recommendation available to explain.")
            return "wait", None
        elif choice.lower() == 'r':
            print_info("Refreshing state and generating a new recommendation...")
            return "refresh", None
        elif choice.lower() == 'm':
            print_info("Manual Mode active. Go play in the Slay the Spire 2 window!")
            input(f"{C_BOLD}Press [Enter] here when you want to hand control back to the AI...{C_RESET}")
            return "wait", None
        elif choice.lower() == 'l':
            print_header("Markdown Game State")
            print(state_markdown)
            return "wait", None
        elif choice.lower() == 'a':
            self.display_valid_actions(state_json)
            return "wait", None
        elif choice.lower() == 'q':
            print_info("Exiting agent runner.")
            sys.exit(0)
        else:
            # Check if user entered a direct JSON action
            try:
                custom_action = json.loads(choice)
                return "execute_custom", custom_action
            except json.JSONDecodeError:
                print_error("Invalid input. Press Enter, 'r' to refresh, 'm' to pause, or type valid JSON.")
                return "wait", None

    def display_valid_actions(self, state_json):
        """Extracts and prints possible actions based on current JSON state."""
        print_header("Suggested Manual Commands")
        state_type = state_json.get("state_type")
        
        if state_type == "menu":
            options = state_json.get("options", [])
            print(f"Menu options available (select using menu_select):")
            for idx, opt in enumerate(options):
                opt_id = opt if isinstance(opt, str) else opt.get("name", str(idx))
                print(f"  - {C_CYAN}{{\"action\": \"menu_select\", \"option\": \"{opt_id}\"}}{C_RESET}")
        
        elif state_type in ["monster", "elite", "boss", "combat"]:
            hand = state_json.get("player", {}).get("hand", [])
            battle = state_json.get("battle", {})
            monsters = battle.get("enemies", [])
            
            print("Hand Cards:")
            first_enemy = monsters[0].get("entity_id") if monsters else "ENEMY_ID_0"
            for idx, card in enumerate(hand):
                if not card.get("can_play", True):
                    continue
                name = card.get("name")
                cost = card.get("cost")
                target_type = card.get("target_type", "None")
                target_req = target_type in ["AnyEnemy", "NormalEnemy", "Enemy"]
                target_str = f', "target": "{first_enemy}"' if target_req else ""
                print(f"  - {C_CYAN}{{\"action\": \"play_card\", \"card_index\": {idx}{target_str}}}{C_RESET} ({name}, Cost: {cost})")
                
            print("Enemies:")
            for m in monsters:
                m_id = m.get("entity_id")
                name = m.get("name")
                hp = m.get("hp")
                intent = m.get("intent", {}).get("name", "Unknown")
                print(f"  - ID: {C_YELLOW}{m_id}{C_RESET} ({name}, HP: {hp}, Intent: {intent})")
                
            print("End turn:")
            print(f"  - {C_CYAN}{{\"action\": \"end_turn\"}}{C_RESET}")
            
        elif state_type == "rewards":
            rewards = state_json.get("rewards", {}).get("rewards", [])
            print("Rewards:")
            for idx, reward in enumerate(rewards):
                print(f"  - {C_CYAN}{{\"action\": \"claim_reward\", \"index\": {idx}}}{C_RESET} ({reward.get('text')})")
            print(f"  - {C_CYAN}{{\"action\": \"proceed\"}}{C_RESET}")
            
        elif state_type == "card_reward":
            cards = state_json.get("card_reward", {}).get("cards", [])
            print("Card Choices:")
            for idx, card in enumerate(cards):
                print(f"  - {C_CYAN}{{\"action\": \"select_card_reward\", \"card_index\": {idx}}}{C_RESET} ({card.get('name')} - {card.get('description')})")
            if state_json.get("card_reward", {}).get("can_skip", False):
                print(f"  - {C_CYAN}{{\"action\": \"skip_card_reward\"}}{C_RESET} (Skip card reward)")
            
        elif state_type == "map":
            nodes = state_json.get("map", {}).get("nodes", [])
            print("Map Nodes:")
            for idx, node in enumerate(nodes):
                if node.get("available", False):
                    print(f"  - {C_CYAN}{{\"action\": \"choose_map_node\", \"index\": {idx}}}{C_RESET} (Type: {node.get('room_type')}, Y-row: {node.get('y')})")
                    
        elif state_type == "rest_site":
            options = state_json.get("rest_site", {}).get("options", [])
            print("Rest Site Options:")
            for idx, opt in enumerate(options):
                if opt.get("is_enabled", True):
                    print(f"  - {C_CYAN}{{\"action\": \"choose_rest_option\", \"index\": {idx}}}{C_RESET} ({opt.get('name')})")
            if state_json.get("rest_site", {}).get("can_proceed", False):
                print(f"  - {C_CYAN}{{\"action\": \"proceed\"}}{C_RESET} (Proceed to map)")

        elif state_type == "event":
            event = state_json.get("event", {})
            options = event.get("options", [])
            print("Event Options:")
            for idx, opt in enumerate(options):
                if not opt.get("is_locked", False):
                    print(f"  - {C_CYAN}{{\"action\": \"choose_event_option\", \"index\": {idx}}}{C_RESET} ({opt.get('title')})")
            if event.get("in_dialogue", False):
                print(f"  - {C_CYAN}{{\"action\": \"advance_dialogue\"}}{C_RESET} (Advance dialogue)")

        elif state_type == "shop":
            items = state_json.get("shop", {}).get("items", [])
            print("Shop Items:")
            for idx, item in enumerate(items):
                name = item.get('card_name') or item.get('relic_name') or item.get('potion_name') or "item"
                if item.get("is_stocked", True) and item.get("can_afford", True):
                    print(f"  - {C_CYAN}{{\"action\": \"shop_purchase\", \"index\": {idx}}}{C_RESET} ({name})")
            print(f"  - {C_CYAN}{{\"action\": \"proceed\"}}{C_RESET} (Leave shop)")

        elif state_type in ["card_select", "hand_select"]:
            cards = state_json.get("card_select", {}).get("cards", [])
            print("Select Cards:")
            for idx, card in enumerate(cards):
                print(f"  - {C_CYAN}{{\"action\": \"select_card\", \"index\": {idx}}}{C_RESET} ({card.get('name')})")
            print(f"  - {C_CYAN}{{\"action\": \"confirm_selection\"}}{C_RESET}")
            print(f"  - {C_CYAN}{{\"action\": \"cancel_selection\"}}{C_RESET}")
            
        elif state_type == "game_over":
            options = state_json.get("game_over", {}).get("options", [])
            print("Game Over Options:")
            for opt in options:
                print(f"  - {C_CYAN}{{\"action\": \"menu_select\", \"option\": \"{opt}\"}}{C_RESET} (Return to main menu)")
                
        elif state_type == "treasure":
            relics = state_json.get("treasure", {}).get("relics", [])
            print("Treasure Relics:")
            for idx, relic in enumerate(relics):
                print(f"  - {C_CYAN}{{\"action\": \"claim_treasure_relic\", \"index\": {idx}}}{C_RESET} ({relic.get('name')})")
            if state_json.get("treasure", {}).get("can_proceed", False):
                print(f"  - {C_CYAN}{{\"action\": \"proceed\"}}{C_RESET} (Proceed to map)")

        else:
            print(f"No custom list parser for state_type '{state_type}'.")
            print("You can send raw actions via JSON. Example: {\"action\": \"proceed\"}")

    def run_loop(self):
        """Starts the agent play loop."""
        print_header("Starting Agent Loop")
        
        while True:
            try:
                # 1. Fetch current game states
                state_json = self.pull_game_state("json")
                state_markdown = self.pull_game_state("markdown")
                
                state_type = state_json.get("state_type", "unknown")
                print(f"\n{C_BOLD}Current Screen State: {C_BLUE}{state_type.upper()}{C_RESET}")
                
                # State tracking signature to clear history on transitions
                round_num = state_json.get("battle", {}).get("round", 0) if state_json.get("battle") else 0
                turn_owner = state_json.get("battle", {}).get("turn", "") if state_json.get("battle") else ""
                sig = (state_type, round_num, turn_owner)
                if sig != self.last_state_signature:
                    self.action_history = []
                    self.last_state_signature = sig
                
                # Check if game is in a play phase
                is_play_phase = state_json.get("is_play_phase", True)
                turn = state_json.get("turn", "player")
                
                if state_type == "combat" or state_type in ["monster", "elite", "boss"]:
                    # Print brief combat summary
                    player_hp = state_json.get("player", {}).get("hp", "?")
                    player_max_hp = state_json.get("player", {}).get("max_hp", "?")
                    energy = state_json.get("player", {}).get("energy", "?")
                    print(f"Player HP: {player_hp}/{player_max_hp} | Energy: {energy} | Turn: {turn}")
                    
                    if not is_play_phase or turn == "enemy":
                        print_info("Waiting for enemy turn... (sleeping 1 second)")
                        time.sleep(1.0)
                        continue
                
                # 2. Get recommendation from Ollama
                ollama_suggestion = self.query_ollama(state_markdown)
                
                # 3. Execute or wait based on mode
                if self.interactive:
                    decision = "wait"
                    while decision == "wait":
                        decision, action = self.display_interactive_menu(state_json, state_markdown, ollama_suggestion)
                    
                    if decision == "execute_ollama":
                        if ollama_suggestion.get("action") == "get_game_state":
                            print_info("Refreshing state as suggested by model...")
                            continue
                        res = self.post_action(ollama_suggestion)
                        status = res.get("message", "success") if res.get("status") != "error" else f"[ERROR] {res.get('error')}"
                        self.action_history.append((ollama_suggestion, status))
                        # Sleep briefly to let animation finish
                        time.sleep(1.5)
                    elif decision == "execute_custom":
                        res = self.post_action(action)
                        status = res.get("message", "success") if res.get("status") != "error" else f"[ERROR] {res.get('error')}"
                        self.action_history.append((action, status))
                        # Sleep briefly to let animation finish
                        time.sleep(1.5)
                else:
                    # Check if user wants to pause before we get/execute next action
                    if self.launched_interactive:
                        self.check_for_pause_request()
                    
                    if self.interactive:
                        continue
                        
                    if ollama_suggestion:
                        if ollama_suggestion.get("action") == "get_game_state":
                            print_info("Automatic refresh triggered by model suggestion.")
                            time.sleep(1.0)
                            continue
                        print(f"{C_YELLOW}Ollama recommends:   {C_BOLD}{json.dumps(ollama_suggestion)}{C_RESET}")
                        if self.last_stats:
                            stats = self.last_stats
                            pct = (stats['prompt_tokens'] / 32768) * 100
                            print(f"{C_CYAN}[Stats] Context: {stats['prompt_tokens']:,} / 32,768 tokens ({pct:.1f}% used) | Gen: {stats['eval_tokens']} tkn ({stats['tokens_per_sec']:.1f} t/s) | Time: {stats['total_s']:.2f}s{C_RESET}")
                        res = self.post_action(ollama_suggestion)
                        status = res.get("message", "success") if res.get("status") != "error" else f"[ERROR] {res.get('error')}"
                        self.action_history.append((ollama_suggestion, status))
                        # Sleep 1.5s in increments to allow responsive pause
                        for _ in range(15):
                            time.sleep(0.1)
                            if self.launched_interactive and self.check_for_pause_request():
                                break
                    else:
                        print_warning("No action generated. Sleeping 3 seconds and retrying...")
                        for _ in range(30):
                            time.sleep(0.1)
                            if self.launched_interactive and self.check_for_pause_request():
                                break
                        
            except httpx.HTTPStatusError as e:
                print_error(f"HTTP Error: {e.response.status_code} - {e.response.text}")
                print_info("Sleeping 3 seconds...")
                time.sleep(3.0)
            except Exception as e:
                print_error(f"Unexpected error in loop: {e}")
                print_info("Sleeping 3 seconds...")
                time.sleep(3.0)

def main():
    parser = argparse.ArgumentParser(description="Slay the Spire 2 local Ollama agent runner.")
    parser.add_argument("--game-url", default="http://localhost:15526", help="REST API URL of the STS2 MCP Mod.")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Local Ollama server API URL.")
    parser.add_argument("--model", default="llama3", help="Ollama model to use (default: llama3).")
    parser.add_argument("--interactive", action="store_true", help="Enable co-op/interactive mode (prompt user before actions).")
    args = parser.parse_args()

    print_header("Slay the Spire 2 AI Agent")
    agent = STS2Agent(args.game_url, args.ollama_url, args.model, args.interactive)
    
    if not agent.check_services():
        print_error("Failed to connect to required services. Exiting.")
        sys.exit(1)
        
    try:
        agent.run_loop()
    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}Agent loop stopped by user.{C_RESET}")
        sys.exit(0)

if __name__ == "__main__":
    main()
