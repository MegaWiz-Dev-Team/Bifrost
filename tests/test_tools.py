"""Tests for Bifrost tools and registry (TDD)."""

import pytest
from bifrost.tools.builtin import GetCurrentTimeTool, CalculateTool, HttpRequestTool
from bifrost.tools.registry import ToolRegistry


# === Tool Tests ===

class TestGetCurrentTimeTool:
    @pytest.fixture
    def tool(self):
        return GetCurrentTimeTool()

    @pytest.mark.asyncio
    async def test_returns_iso_format(self, tool):
        result = await tool.execute()
        assert "T" in result  # ISO 8601 format
        assert "+" in result or "Z" in result  # timezone

    def test_openai_schema(self, tool):
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "get_current_time"


class TestCalculateTool:
    @pytest.fixture
    def tool(self):
        return CalculateTool()

    @pytest.mark.asyncio
    async def test_basic_addition(self, tool):
        result = await tool.execute(expression="2 + 3")
        assert result == "5.0"

    @pytest.mark.asyncio
    async def test_multiplication(self, tool):
        result = await tool.execute(expression="4 * 5")
        assert result == "20.0"

    @pytest.mark.asyncio
    async def test_complex_expression(self, tool):
        result = await tool.execute(expression="(2 + 3) * 4 - 1")
        assert result == "19.0"

    @pytest.mark.asyncio
    async def test_power(self, tool):
        result = await tool.execute(expression="2 ** 10")
        assert result == "1024.0"

    @pytest.mark.asyncio
    async def test_division(self, tool):
        result = await tool.execute(expression="10 / 3")
        assert float(result) == pytest.approx(3.333, rel=0.01)

    @pytest.mark.asyncio
    async def test_division_by_zero(self, tool):
        result = await tool.execute(expression="1 / 0")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_invalid_expression(self, tool):
        result = await tool.execute(expression="import os")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_negative_numbers(self, tool):
        result = await tool.execute(expression="-5 + 3")
        assert result == "-2.0"

    def test_openai_schema(self, tool):
        schema = tool.to_openai_schema()
        assert schema["function"]["name"] == "calculate"
        assert "expression" in schema["function"]["parameters"]["properties"]


class TestHttpRequestTool:
    def test_openai_schema(self):
        tool = HttpRequestTool()
        schema = tool.to_openai_schema()
        assert schema["function"]["name"] == "http_request"
        assert "url" in schema["function"]["parameters"]["properties"]


# === Registry Tests ===

class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = GetCurrentTimeTool()
        reg.register(tool)
        assert reg.get("get_current_time") is tool

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register(GetCurrentTimeTool())
        reg.register(CalculateTool())
        assert len(reg.list_tools()) == 2

    def test_get_openai_tools(self):
        reg = ToolRegistry()
        reg.register(GetCurrentTimeTool())
        reg.register(CalculateTool())
        schemas = reg.get_openai_tools()
        assert len(schemas) == 2
        assert all(s["type"] == "function" for s in schemas)

    def test_contains(self):
        reg = ToolRegistry()
        reg.register(CalculateTool())
        assert "calculate" in reg
        assert "nonexistent" not in reg

    def test_get_unknown_tool(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_len(self):
        reg = ToolRegistry()
        assert len(reg) == 0
        reg.register(CalculateTool())
        assert len(reg) == 1
