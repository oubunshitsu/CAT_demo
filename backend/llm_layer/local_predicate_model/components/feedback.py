from collections import defaultdict
import json


class FeedbackTemplateBased:
    def __init__(self):
        with (
            open("data/static/ptn_feedback_template.json", "r") as f1,
            open("data/static/predicate_feedback_template.json", "r") as f2,
            open("data/static/ia_info.json", "r") as f3,
            open("data/static/ptn_desc.json", "r") as f4,
        ):
            self.ptn_feedback_template = json.loads(f1.read())
            self.predicate_feedback_template = json.loads(f2.read())
            self.ia_info = json.loads(f3.read())
            self.ptn_desc_template = json.loads(f4.read())

    def get_ptn_feedback(self, ia_id, predicted_ptns, predicted_slots):
        results = defaultdict(list)
        for ptn in predicted_ptns:
            fdb_templates_current_ptn = self.ptn_feedback_template[str(ptn)]
            for template in fdb_templates_current_ptn:
                slot = (
                    predicted_slots[ptn][0]
                    if ptn in predicted_slots
                    else "<placeholder>"
                )
                fdb_current_ptn = template.format(z=slot, **self.ia_info[ia_id])
                results[ptn].append(fdb_current_ptn)
        return dict(results)

    def get_predicate_feedback(self, ia_id, yes_predicates, predicate_results):
        results = []
        if {"ack-c", "deny-c"}.issubset(set(yes_predicates)):
            rationale_ack_c = (
                predicate_results["ack-c"]["evidence"]
                if "evidence" in predicate_results["ack-c"]
                else "<placeholder>"
            )
            rationale_deny_c = (
                predicate_results["deny-c"]["evidence"]
                if "evidence" in predicate_results["deny-c"]
                else "<placeholder>"
            )
            rationale = (
                "First, " + rationale_ack_c + "On top of that, " + rationale_deny_c
            )
            feedback = self.predicate_feedback_template["weak_contradict"].format(
                rationale=rationale, **self.ia_info[ia_id]
            )
        elif {"ack-c", "reverse-c"}.issubset(set(yes_predicates)):
            rationale_ack_c = (
                predicate_results["ack-c"]["evidence"]
                if "evidence" in predicate_results["ack-c"]
                else "<placeholder>"
            )
            rationale_reverse_c = (
                predicate_results["reverse-c"]["evidence"]
                if "evidence" in predicate_results["reverse-c"]
                else "<placeholder>"
            )
            rationale = (
                "First, " + rationale_ack_c + "On top of that, " + rationale_reverse_c
            )
            feedback = self.predicate_feedback_template["strong_contradict"].format(
                rationale=rationale, **self.ia_info[ia_id]
            )
        else:
            feedback = None
        if feedback is not None:
            results.append(feedback)
        return results

    def get_ptn_description(self, ia_id, predicted_ptns, predicted_slots):
        results = {}
        for ptn in predicted_ptns:
            slot = (
                predicted_slots[ptn][0] if ptn in predicted_slots else "<placeholder>"
            )
            results[ptn] = self.ptn_desc_template[str(ptn)].format(
                z=slot, **self.ia_info[ia_id]
            )
        return results
