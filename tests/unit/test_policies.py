import json
import unittest
from pathlib import Path

from policies.grounding import ungrounded_rule_ids
from policies.tool_scope import AGENT_TOOLS, NODE_TOOLS, REVIEWER_ONLY


class ToolScope(unittest.TestCase):
    def test_registry_matches_tools_json_and_no_node_can_decide(self):
        spec = json.loads(Path("agent/tools.json").read_text(encoding="utf-8"))
        names = {t["name"] for t in spec["tools"]}
        self.assertEqual(names, AGENT_TOOLS)
        for node, tools in NODE_TOOLS.items():
            self.assertTrue(tools <= AGENT_TOOLS, node)
            self.assertFalse(tools & REVIEWER_ONLY, node)


class Grounding(unittest.TestCase):
    def test_ungrounded_rule_ids_detected(self):
        res = [{"blockers": [{"rule_id": "MRI-LS-02"}]}]
        self.assertEqual(ungrounded_rule_ids("Missing per MRI-LS-02.", res), set())
        self.assertEqual(ungrounded_rule_ids("Per MRI-LS-09 you need more.", res), {"MRI-LS-09"})
