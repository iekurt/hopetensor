import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.main import TaskResponse, TaskStatus, process_task, utc_now
from app.utils.validation import ensure_finite_number, parse_number_list


class ValidationTests(unittest.TestCase):
    def test_ensure_finite_number_accepts_numeric_values(self):
        self.assertEqual(ensure_finite_number("2.5", field_name="x"), 2.5)

    def test_ensure_finite_number_rejects_bool(self):
        with self.assertRaisesRegex(ValueError, "must be a number, not boolean"):
            ensure_finite_number(True, field_name="x")

    def test_ensure_finite_number_rejects_non_finite(self):
        with self.assertRaisesRegex(ValueError, "must be finite"):
            ensure_finite_number(float("inf"), field_name="x")

    def test_parse_number_list_rejects_non_list(self):
        with self.assertRaisesRegex(ValueError, "payload.numbers must be a list"):
            parse_number_list("not-a-list", field_name="numbers")


class ProcessTaskTests(unittest.TestCase):
    def _task(self, payload):
        now = utc_now()
        return TaskResponse(
            id="t1",
            type="sum_numbers",
            payload=payload,
            status=TaskStatus.pending,
            created_at=now,
            updated_at=now,
        )

    def _run_process_task(self, payload):
        with patch("app.main.asyncio.sleep", new=AsyncMock()):
            return asyncio.run(process_task(self._task(payload)))

    def test_sum_numbers_success(self):
        result = self._run_process_task({"numbers": [1, "2", 3.5]})
        self.assertEqual(result["numbers"], [1.0, 2.0, 3.5])
        self.assertEqual(result["total"], 6.5)

    def test_sum_numbers_rejects_nan(self):
        with self.assertRaisesRegex(ValueError, "payload.numbers\[1\] must be finite"):
            self._run_process_task({"numbers": [1, float("nan")]})

    def test_sum_numbers_rejects_boolean(self):
        with self.assertRaisesRegex(ValueError, "payload.numbers\[0\] must be a number, not boolean"):
            self._run_process_task({"numbers": [True, 2]})


if __name__ == "__main__":
    unittest.main()
