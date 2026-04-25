"""
VEGA AI — Finance Agent
Tracks budgets, expenses, invoices, and provides financial summaries.
"""

import json
from agents import BaseAgent, AgentResult

FINANCE_SYSTEM = """You are VEGA's Finance Agent. You help track personal finances including:
- Budget management and expense tracking
- Invoice generation and tracking
- Financial summaries and spending analysis
- Savings goals and projections

Present financial data in clear tables when appropriate.
Always use the user's preferred currency.
Never provide investment advice — only factual tracking and analysis."""


class FinanceAgent(BaseAgent):
    name = "finance"
    description = "Tracks budgets, expenses, invoices, and financial summaries"
    capabilities = ["budget", "expenses", "invoice", "finance", "money"]

    async def run(self, task: str, context: dict) -> AgentResult:
        # Load financial data from memory
        finance_data = self.memory.procedural.get_preference("finance_data", {})
        data_ctx = ""
        if finance_data:
            data_ctx = f"\n\nCurrent financial data: {json.dumps(finance_data, indent=2)[:1000]}"

        response = await self.router.query(
            prompt=task + data_ctx,
            system=FINANCE_SYSTEM,
            task_type="analysis",
            temperature=0.3,
            max_tokens=3000
        )

        return AgentResult(success=response.success, output=response.text)
