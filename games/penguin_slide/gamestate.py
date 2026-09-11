"""Handles the state and output for a single simulation round."""

import random

from game_override import GameStateOverride
from game_events import slide_start_event, tile_result_event, slide_summary_event
from src.calculations.statistics import get_random_outcome
from src.events.event_constants import EventConstants


class GameState(GameStateOverride):
    """Handle all game-logic and event updates for a given simulation number."""

    def run_spin(self, sim, simulation_seed=None):
        self.reset_seed(sim, simulation_seed)
        self.repeat = True
        while self.repeat:
            self.reset_book()

            def quantize(value: float) -> float:
                return round(value + 1e-9, 1)

            current_value = quantize(float(self.config.starting_value))
            self.starting_value = current_value
            has_lifering = False
            self.has_lifering = has_lifering
            steps = 0
            result = "slip"

            tile_distribution = self.config.tile_probs
            lane_distribution = {lane: 1 for lane in self.config.lane_offsets}
            last_lane = get_random_outcome(lane_distribution)
            last_change_step = 0
            slide_start_event(self)

            while steps < self.config.max_steps:
                steps += 1
                items = []
                forced_lane = None
                forced_type = None
                item_count = int(get_random_outcome(self.config.step_item_counts))
                item_count = min(item_count, len(self.config.lane_offsets))
                lanes = random.sample(self.config.lane_offsets, item_count)

                for lane in lanes:
                    tile_type = get_random_outcome(tile_distribution)
                    item = {"type": tile_type, "lane": lane}
                    if tile_type == "coin":
                        tier = get_random_outcome(self.config.coin_values)
                        if isinstance(tier, str) and tier in self.config.coin_value_tiers:
                            low, high = self.config.coin_value_tiers[tier]
                            if tier == "bronze":
                                # Bias toward sub-1 values so they appear more often.
                                if random.random() < 0.7:
                                    value = round(random.uniform(low, 1.0), 1)
                                else:
                                    value = round(random.uniform(1.0, high), 1)
                            else:
                                value = round(random.uniform(low, high), 1)
                        else:
                            value = float(tier)
                        value = max(self.config.coin_value_min, min(self.config.coin_value_max, value))
                        item["coinValue"] = value
                    elif tile_type == "star":
                        item["multiplier"] = int(get_random_outcome(self.config.star_multipliers))
                    items.append(item)

                if steps == self.config.max_steps:
                    forced_lane = get_random_outcome(lane_distribution)
                    forced_type = get_random_outcome({"goal": 1, "banana": 1})
                    items = [item for item in items if item["lane"] != forced_lane]
                    items.append({"type": forced_type, "lane": forced_lane})

                lane_types = {lane: "empty" for lane in self.config.lane_offsets}
                for item in items:
                    lane_types[item["lane"]] = item["type"]

                safe_lanes = [lane for lane, t in lane_types.items() if t != "banana"]
                item_lanes = [lane for lane, t in lane_types.items() if t != "empty"]
                can_change = (steps - last_change_step) >= int(self.config.min_lane_change_steps)
                if forced_lane is not None and forced_lane != last_lane and not can_change:
                    items = [item for item in items if item["lane"] != forced_lane]
                    forced_lane = last_lane
                    items.append({"type": forced_type, "lane": forced_lane})
                    lane_types = {lane: "empty" for lane in self.config.lane_offsets}
                    for item in items:
                        lane_types[item["lane"]] = item["type"]
                    safe_lanes = [lane for lane, t in lane_types.items() if t != "banana"]
                if forced_lane is not None:
                    candidate_lane = forced_lane
                elif item_lanes:
                    if self.config.avoid_banana and safe_lanes and random.random() < self.config.avoid_banana_chance:
                        candidate_lane = random.choice(safe_lanes)
                    else:
                        candidate_lane = random.choice(item_lanes)
                else:
                    candidate_lane = get_random_outcome(lane_distribution)
                if abs(candidate_lane - last_lane) > 1:
                    candidate_lane = last_lane
                if candidate_lane != last_lane and not can_change:
                    penguin_lane = last_lane
                else:
                    penguin_lane = candidate_lane
                    if penguin_lane != last_lane:
                        last_lane = penguin_lane
                        last_change_step = steps
                hit_item = None
                for item in items:
                    if item["lane"] == penguin_lane:
                        hit_item = item
                        break

                hit_type = hit_item["type"] if hit_item else "empty"
                detail = {"laneOffset": int(penguin_lane), "items": items, "hitType": hit_type}

                if hit_type == "goal":
                    if steps < self.config.min_steps:
                        tile_result_event(self, steps, "empty", current_value, detail)
                        continue
                    result = "goal"
                    tile_result_event(self, steps, "goal", current_value, detail)
                    break

                if hit_type == "coin":
                    coin_value = hit_item["coinValue"]
                    coin_value = max(self.config.coin_value_min, min(self.config.coin_value_max, coin_value))
                    current_value = quantize(current_value + float(coin_value))
                    detail["coinValue"] = float(coin_value)
                    tile_result_event(self, steps, "coin", current_value, detail)
                    continue

                if hit_type == "star":
                    mult = hit_item["multiplier"]
                    current_value = quantize(current_value * float(mult))
                    detail["multiplier"] = int(mult)
                    tile_result_event(self, steps, "star", current_value, detail)
                    continue

                if hit_type == "lifering":
                    has_lifering = True
                    self.has_lifering = True
                    detail["gained"] = True
                    tile_result_event(self, steps, "lifering", current_value, detail)
                    continue

                if hit_type == "banana":
                    is_high_win = current_value >= self.config.starting_value * self.config.high_win_threshold
                    fall_prob = self.config.banana_fall_prob * (self.config.high_win_slip_mult if is_high_win else 1.0)
                    fall_prob = min(1.0, fall_prob)
                    fall = get_random_outcome({True: fall_prob, False: 1 - fall_prob})
                    if fall:
                        if steps < self.config.min_steps:
                            current_value = quantize(current_value * 0.5)
                            detail["fall"] = False
                            detail["lostHalf"] = True
                            tile_result_event(self, steps, "banana", current_value, detail)
                            continue
                        if has_lifering:
                            has_lifering = False
                            self.has_lifering = False
                            detail["fall"] = False
                            detail["savedByLifering"] = True
                            tile_result_event(self, steps, "banana", current_value, detail)
                            continue
                        current_value = 0.0
                        detail["fall"] = True
                        tile_result_event(self, steps, "banana", current_value, detail)
                        result = "slip"
                        break

                    if has_lifering:
                        has_lifering = False
                        self.has_lifering = False
                        detail["fall"] = False
                        detail["savedByLifering"] = True
                        tile_result_event(self, steps, "banana", current_value, detail)
                        continue
                    current_value = quantize(current_value * 0.5)
                    detail["fall"] = False
                    detail["lostHalf"] = True
                    tile_result_event(self, steps, "banana", current_value, detail)
                    continue

                tile_result_event(self, steps, "empty", current_value, detail)

            if steps >= self.config.max_steps and result != "goal":
                result = "goal"

            slide_summary_event(self, steps, current_value, result)

            if result == "goal":
                self.win_manager.update_spinwin(current_value)
            else:
                self.win_manager.update_spinwin(0.0)

            self.win_manager.update_gametype_wins(self.gametype)

            game_event = {
                "index": len(self.book.events),
                "type": EventConstants.WIN_DATA.value,
                "totalWin": int(round(current_value * 100, 0)) if result == "goal" else 0,
                "result": result,
                "steps": int(steps),
            }
            self.book.add_event(game_event)

            self.evaluate_finalwin()

        self.imprint_wins()

    def run_freespin(self):
        pass
