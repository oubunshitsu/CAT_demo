from collections import defaultdict
import pandas as pd


class InstancePtnAggregator:
    def __init__(self):
        pass

    def __call__(self, predicate_results):
        """
        Given a Dict that contains predicate-level results,
        aggregate to get the ptn-level results, ptn, slot, and evidence

        """
        # Get ptns from predictes
        ptns_predicates_map = {
            # 1: ["ack-c", "miti"],
            1: ["miti"],
            # 2: ["ack-c", "ano-z"],
            2: ["ano-z"],
            3: ["no-evi"],
            4: ["deny-c", "ano-z"],
            5: ["reverse-c", "trans1"],
            6: ["reverse-c", "trans2"],
            7: ["no-need-address"],
            # 8: ["y-pro-opposite-z", "y-sup-same-z"],
            81: ["y-pro-opposite-z"],
            82: ["y-sup-same-z"],
            9: ["x-pro-z"],
            10: ["x-sup-z"],
        }
        ptn_level_results = {}

        assert len(predicate_results) == 13, (
            "predicate_results has less than 13 predicates"
        )
        # Get all predicates to which the answer is "yes"
        yes_predicates = []
        for predicate, results_per_predicate in predicate_results.items():
            if results_per_predicate["answer"] == "yes":
                yes_predicates.append(predicate)

        # Get ptns
        result_ptns = []
        for ptn, predicates in ptns_predicates_map.items():
            # if ptn == 8:
            #     if set(predicates) & set(yes_predicates):
            #         result_ptns.append(ptn)
            # else:
            #     if set(predicates).issubset(set(yes_predicates)):
            #         result_ptns.append(ptn)
            if set(predicates).issubset(set(yes_predicates)):
                result_ptns.append(ptn)
        ptn_level_results["ptn"] = result_ptns

        # Get slots and evidence based on the ptns
        result_slots = defaultdict(list)
        result_evidence = defaultdict(list)
        for key, d in dict(
            zip(["slot", "evidence"], [result_slots, result_evidence])
        ).items():
            for ptn in result_ptns:
                predicates = ptns_predicates_map[ptn]
                for predicate in predicates:
                    if key in predicate_results[predicate]:
                        d[ptn].append(predicate_results[predicate][key])
            ptn_level_results[key] = dict(d)

        # breakpoint()

        return yes_predicates, ptn_level_results


class BatchPtnAggregator:
    def __init__(self):
        pass

    def __call__(self, predicate_results_df):
        """
        Given a DataFrame that contains predicate-level results,
        aggregate to get the ptn-level results, ptns and slots.

        """
        # Get ptns from predictes
        ptns_predicates_map = {
            1: ["ack-c", "miti"],
            2: ["ack-c", "ano-z"],
            3: ["no-evi"],
            4: ["deny-c", "ano-z"],
            5: ["reverse-c", "trans1"],
            6: ["reverse-c", "trans2"],
            7: ["no-need-address"],
            8: ["y-pro-opposite-z", "y-sup-same-z"],
            9: ["x-pro-z"],
            10: ["x-sup-z"],
        }
        ptn_level_results = []
        for ca_id, indices in predicate_results_df.groupby("ca_id").groups.items():
            ca_group_df = predicate_results_df.loc[indices]
            assert len(ca_group_df) == 13, f"{ca_id} has less than 13 predicates"
            yes_predicates = ca_group_df[(ca_group_df.predicted_answer == "yes")][
                "predicate"
            ].tolist()

            # Get ptns
            result_ptns = []
            for ptn, predicates in ptns_predicates_map.items():
                if ptn == 8:
                    if set(predicates) & set(yes_predicates):
                        result_ptns.append(ptn)
                else:
                    if set(predicates).issubset(set(yes_predicates)):
                        result_ptns.append(ptn)

            # Get slots based on the ptns
            result_slots = defaultdict(list)
            for ptn in result_ptns:
                predicates = ptns_predicates_map[ptn]
                for predicate in predicates:
                    row = ca_group_df[ca_group_df.predicate == predicate]
                    slot = row.squeeze()["predicted_slot"]

                    # breakpoint()

                    if isinstance(slot, str):
                        result_slots[ptn].append(slot)

            # Create a new ptn level df
            new_row = {
                key: value
                for key, value in ca_group_df.iloc[0].to_dict().items()
                if key in ["ia_id", "ia", "ca_id", "ca"]
            }
            new_row["predicted_ptns"] = result_ptns
            new_row["predicted_slots"] = result_slots
            ptn_level_results.append(new_row)
        ptn_level_results_df = pd.DataFrame(ptn_level_results)
        return ptn_level_results_df
