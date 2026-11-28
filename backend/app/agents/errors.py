"""Errors shared by all agents."""


class AgentEscalation(Exception):
    """An agent could not produce a valid result, so a human must take over (Contracts section 3)."""