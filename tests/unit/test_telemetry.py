import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from rotation.telemetry import publish


class TelemetryTests(unittest.TestCase):
    def test_metrics_use_ingestion_endpoint_and_publish(self):
        client = SimpleNamespace(
            base_client=SimpleNamespace(endpoint='https://telemetry.us-ashburn-1.oraclecloud.com/20180401'),
            post_metric_data=Mock(return_value=SimpleNamespace(data=SimpleNamespace(failed_metrics_count=0))),
        )
        config = SimpleNamespace(compartment_id='compartment', db_system_id='database',
                                 username='demo', rotation_days=30)
        with patch('cli.runtime.clients', return_value=({}, {})), \
                patch('rotation.telemetry.oci.monitoring.MonitoringClient', return_value=client), \
                patch('rotation.telemetry.snapshot', return_value={}):
            publish(config, object())
        self.assertEqual(client.base_client.endpoint,
                         'https://telemetry-ingestion.us-ashburn-1.oraclecloud.com/20180401')
        client.post_metric_data.assert_called_once()
        metrics = client.post_metric_data.call_args.args[0].metric_data
        self.assertEqual({m.name for m in metrics}, {'RotationFailure', 'MonitorHeartbeat'})
