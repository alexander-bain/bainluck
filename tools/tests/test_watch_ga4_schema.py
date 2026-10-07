import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("schema", Path(__file__).parents[1] / "watch_ga4_schema.py")
schema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schema)


class WatchSchemaTests(unittest.TestCase):
    def test_plan_is_idempotent_and_event_scoped(self):
        ops = schema.plan([], [])
        self.assertEqual(len(ops), 11)
        dimensions = [body for kind, body in ops if kind == "customDimensions"]
        metrics = [body for kind, body in ops if kind == "customMetrics"]
        self.assertTrue(all(body["scope"] == "EVENT" for _, body in ops))
        self.assertEqual(schema.plan(dimensions, metrics), [])
        wrong_scope = [{**body, "scope": "USER"} for body in dimensions]
        self.assertEqual(len(schema.plan(wrong_scope, metrics)), 7)

    def test_schema_excludes_identity(self):
        names = {body["parameterName"] for _, body in schema.plan([], [])}
        self.assertFalse(names & {"email", "user_id", "watchEpoch", "phoneEpoch", "id", "query"})
        self.assertTrue({"device_class", "surface", "first_card_ms", "duration_ms", "app_build"} <= names)

    def test_credential_input_formats(self):
        value = {"client_email": "test@example.invalid", "type": "service_account"}
        raw = json.dumps(value)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "credentials.json"
            path.write_text(raw)
            self.assertEqual(schema.credential_info(raw), value)
            self.assertEqual(schema.credential_info(str(path)), value)
            self.assertEqual(schema.credential_info(base64.b64encode(raw.encode()).decode()), value)
        with self.assertRaises(Exception):
            schema.credential_info("invalid")
