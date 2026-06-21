# ============================================================================
# Secrets Manager - Secure storage for API keys
# ============================================================================

resource "aws_secretsmanager_secret" "tavily_api_key" {
  name                    = "${var.stack_name}/tavily-api-key"
  description             = "Tavily Search API key for Specialist and Fact Checker agents"
  recovery_window_in_days = 7

  tags = {
    Name   = "${var.stack_name}-tavily-secret"
    Module = "Security"
  }
}

resource "aws_secretsmanager_secret_version" "tavily_api_key" {
  secret_id     = aws_secretsmanager_secret.tavily_api_key.id
  secret_string = var.tavily_api_key
}
