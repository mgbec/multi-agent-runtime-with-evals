# ============================================================================
# Bedrock Guardrail - Content filtering for all agents
# ============================================================================

resource "aws_bedrock_guardrail" "agent_guardrail" {
  name                      = "${var.stack_name}-guardrail"
  description               = "Content filtering guardrail for multi-agent system"
  blocked_input_messaging   = "Your request was blocked by our content safety policy. Please rephrase your question."
  blocked_outputs_messaging = "The response was blocked by our content safety policy."

  content_policy_config {
    filters_config {
      type            = "HATE"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "INSULTS"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "SEXUAL"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "VIOLENCE"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "MISCONDUCT"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
  }

  sensitive_information_policy_config {
    pii_entities_config {
      type   = "AWS_ACCESS_KEY"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "AWS_SECRET_KEY"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "CREDIT_DEBIT_CARD_NUMBER"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "US_SOCIAL_SECURITY_NUMBER"
      action = "BLOCK"
    }
  }

  tags = {
    Name   = "${var.stack_name}-guardrail"
    Module = "Security"
  }
}

resource "aws_bedrock_guardrail_version" "agent_guardrail" {
  guardrail_arn = aws_bedrock_guardrail.agent_guardrail.guardrail_arn
  description   = "Initial version"
}
