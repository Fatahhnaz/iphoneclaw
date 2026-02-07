import unittest

from iphoneclaw.parse.action_parser import parse_predictions


class TestActionParser(unittest.TestCase):
    def test_thought_multiline_is_joined(self) -> None:
        text = "Thought: a\nThought: b\nAction: wait()"
        pred = parse_predictions(text)[0]
        self.assertEqual(pred.thought, "a\nb")

    def test_action_parsed(self) -> None:
        text = "Thought: x\nAction: click(start_box='(10,20)')"
        pred = parse_predictions(text)[0]
        self.assertEqual(pred.action_type, "click")
        self.assertEqual(pred.action_inputs.start_box, "(10,20)")

    def test_start_box_space_separated_point(self) -> None:
        text = "Thought: x\nAction: click(start_box='<|box_start|>604 606<|box_end|>')"
        pred = parse_predictions(text)[0]
        self.assertEqual(pred.action_type, "click")
        self.assertEqual(pred.action_inputs.start_box, "604 606")

    def test_scroll_without_start_box_is_parsed(self) -> None:
        text = "Thought: x\nAction: scroll(direction='left')"
        pred = parse_predictions(text)[0]
        self.assertEqual(pred.action_type, "scroll")
        self.assertEqual(pred.action_inputs.direction, "left")
        self.assertIsNone(pred.action_inputs.start_box)

    def test_point_param_is_normalized_to_start_box(self) -> None:
        text = "Thought: x\nAction: click(point='<point>510 150</point>')"
        pred = parse_predictions(text)[0]
        self.assertEqual(pred.action_type, "click")
        self.assertIsNotNone(pred.action_inputs.start_box)

    def test_hotkey_param_alias(self) -> None:
        text = "Action: hotkey(hotkey='ctrl v')"
        pred = parse_predictions(text)[0]
        self.assertEqual(pred.action_type, "hotkey")
        self.assertEqual(pred.action_inputs.key, "ctrl v")


if __name__ == "__main__":
    unittest.main()

