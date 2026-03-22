"""Playwright E2E test for Admin agent management UI.

Requires:
  - Backend running on PORT (default 9090) with PLATFORM=web, DASHBOARD_PASSWORD, AUTH_SECRET
  - Frontend running on FRONTEND_PORT (default 3002) with API_URL pointing to backend
  - pip install playwright && playwright install chromium

Usage:
  pytest tests/test_admin_agent_ui.py -v --headed  # visible browser
  pytest tests/test_admin_agent_ui.py -v            # headless
"""

import os
import uuid

import pytest

BASE_URL = os.environ.get("FRONTEND_URL", "http://localhost:3002")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "liliangyu@gmail.com")
ADMIN_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "admin")


@pytest.fixture(scope="module")
def browser_context():
    """Launch browser and login once for all tests."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not os.environ.get("HEADED"))
        context = browser.new_context()
        page = context.new_page()

        # Login
        page.goto(f"{BASE_URL}/login")
        page.fill('input[type="email"]', ADMIN_EMAIL)
        page.fill('input[type="password"]', ADMIN_PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_timeout(3000)

        if "/login" in page.url:
            browser.close()
            pytest.skip("Login failed — backend auth not configured")

        yield context, page

        browser.close()


@pytest.fixture
def page(browser_context):
    _, page = browser_context
    return page


def _unique_id():
    return f"test-{uuid.uuid4().hex[:8]}"


class TestAdminAgentCRUD:
    """Test agent create, edit, and deactivate from the Admin page."""

    def test_admin_page_loads(self, page):
        page.goto(f"{BASE_URL}/admin")
        page.wait_for_timeout(2000)
        assert page.locator("text=Agents (").count() > 0
        assert page.locator('button:has-text("Create Agent")').count() > 0

    def test_create_agent(self, page):
        agent_id = _unique_id()
        page.goto(f"{BASE_URL}/admin")
        page.wait_for_selector("text=Agents (", timeout=5000)

        # Open form
        page.click('button:has-text("Create Agent")')
        page.wait_for_selector("text=New Agent", timeout=3000)

        # Fill
        page.fill("#agent-id", agent_id)
        page.fill("#agent-name", "PW Test Agent")
        page.fill("#agent-role", "Tester")
        page.fill("#agent-personality", "Test personality.")
        page.click('button:has-text("MiniMax M2.7")')

        # Submit
        page.get_by_role("button", name="Create Agent").nth(1).click()
        page.wait_for_timeout(5000)

        content = page.text_content("body")
        assert agent_id in content, f"Agent {agent_id} not found after create"
        assert "PW Test Agent" in content

        # Store for later tests
        self.__class__._created_agent_id = agent_id

    def test_edit_agent(self, page):
        agent_id = getattr(self.__class__, "_created_agent_id", None)
        if not agent_id:
            pytest.skip("No agent created in previous test")

        page.goto(f"{BASE_URL}/admin")
        page.wait_for_selector("text=Agents (", timeout=5000)

        row = page.locator("div.border.rounded-lg", has_text=agent_id)
        row.locator('button:has-text("Edit")').click()
        page.wait_for_timeout(1000)

        page.fill("#agent-name", "PW Updated Agent")
        page.get_by_role("button", name="Update Agent").click()
        page.wait_for_timeout(3000)

        content = page.text_content("body")
        assert "PW Updated Agent" in content
        assert "Agent updated" in content

    def test_deactivate_agent(self, page):
        agent_id = getattr(self.__class__, "_created_agent_id", None)
        if not agent_id:
            pytest.skip("No agent created in previous test")

        page.goto(f"{BASE_URL}/admin")
        page.wait_for_selector("text=Agents (", timeout=5000)

        row = page.locator("div.border.rounded-lg", has_text=agent_id)
        row.locator('button:has-text("Deactivate")').click()
        page.wait_for_timeout(3000)

        content = page.text_content("body")
        assert "deactivated" in content.lower()


class TestChat:
    """Test chat functionality."""

    def test_send_message_and_receive_response(self, page):
        page.goto(f"{BASE_URL}/chat")
        page.wait_for_timeout(2000)

        textarea = page.locator("textarea").first
        textarea.fill("Say hello in exactly 3 words.")
        page.locator('button:has-text("Send")').click()

        # Wait for response (up to 60s)
        for _ in range(30):
            page.wait_for_timeout(2000)
            if page.locator("text=Thinking...").count() == 0:
                break

        content = page.text_content("body")
        # Should have more content than just our message
        assert "Say hello" in content
        assert len(content) > 200, "Expected LLM response in page content"
