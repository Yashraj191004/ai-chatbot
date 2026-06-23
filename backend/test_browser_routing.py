import unittest

from main import wants_open_browser_read


class BrowserReadRoutingTests(unittest.TestCase):
    def test_uploaded_assignment_requests_are_not_browser_commands(self):
        prompts = [
            "Summarize the assignment.",
            "What are the tasks worth 5 marks?",
            (
                '"What is the due date?" "Summarize the assignment." '
                '"What are the tasks worth 5 marks?" '
                '"Generate a study plan for completing this assignment." '
                '"Create 5 quiz questions based on the assignment."'
            ),
        ]

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertFalse(wants_open_browser_read(prompt.lower()))

    def test_explicit_browser_requests_still_route_to_browser(self):
        prompts = [
            "Read the open page.",
            "Summarize the current page.",
            "What does it say on the website?",
            "Look at the page in Chrome.",
        ]

        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertTrue(wants_open_browser_read(prompt.lower()))


if __name__ == "__main__":
    unittest.main()
