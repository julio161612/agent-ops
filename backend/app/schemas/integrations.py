from pydantic import BaseModel, Field, HttpUrl


class SlackWebhookConfigure(BaseModel):
    webhook_url: HttpUrl = Field(description="A Slack 'Incoming Webhook' URL for one channel.")


class SlackIntegrationRead(BaseModel):
    configured: bool
    masked_webhook_url: str | None = Field(
        default=None,
        description="Never the full URL — it's a bearer secret, same treatment as an API key.",
    )


class SlackTestResult(BaseModel):
    sent: bool
    detail: str
