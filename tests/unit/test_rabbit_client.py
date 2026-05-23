from unittest.mock import MagicMock, patch

import pytest

from shared.rabbit import RabbitClient, RabbitConnectionError

QUEUES = [
    "document.parse.requested",
    "document.translate.requested",
    "document.embed.requested",
    "document.index.requested",
    "document.intelligence.requested",
    "document.alert.requested",
    "document.enrich.requested",
]
DLQ_QUEUES = [q.replace("requested", "dead") for q in QUEUES]


@patch("shared.rabbit.pika.BlockingConnection")
def test_declare_topology_creates_all_queues(mock_conn_cls):
    mock_channel = MagicMock()
    mock_conn_cls.return_value.channel.return_value = mock_channel

    client = RabbitClient("amqp://guest:guest@localhost/")
    client.connect()
    client.declare_topology()

    mock_channel.exchange_declare.assert_any_call(
        exchange="tomorrowland.documents",
        exchange_type="topic",
        durable=True,
    )
    mock_channel.exchange_declare.assert_any_call(
        exchange="tomorrowland.documents.dlq",
        exchange_type="fanout",
        durable=True,
    )
    declared_queues = [c.kwargs["queue"] for c in mock_channel.queue_declare.call_args_list]
    for q in QUEUES:
        assert q in declared_queues
    for q in DLQ_QUEUES:
        assert q in declared_queues


@patch("shared.rabbit.pika.BlockingConnection")
def test_publish_returns_message_id(mock_conn_cls):
    mock_channel = MagicMock()
    mock_conn_cls.return_value.channel.return_value = mock_channel

    client = RabbitClient("amqp://guest:guest@localhost/")
    client.connect()
    client.declare_topology()

    msg_id = client.publish(
        "document.parse.requested",
        {"job_id": "abc", "document_id": "def"},
    )
    assert isinstance(msg_id, str) and len(msg_id) == 36
    mock_channel.basic_publish.assert_called_once()


@patch("shared.rabbit.pika.BlockingConnection", side_effect=Exception("refused"))
def test_connect_raises_rabbit_connection_error(mock_conn_cls):
    client = RabbitClient("amqp://guest:guest@localhost/")
    with pytest.raises(RabbitConnectionError):
        client.connect()


@patch("shared.rabbit.pika.BlockingConnection")
def test_noop_when_disabled(mock_conn_cls):
    client = RabbitClient("amqp://guest:guest@localhost/", enabled=False)
    client.connect()
    client.declare_topology()
    msg_id = client.publish("document.parse.requested", {})
    assert msg_id == ""
    mock_conn_cls.assert_not_called()
