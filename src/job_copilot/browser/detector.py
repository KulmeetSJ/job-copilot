"""DOM Form Inspector and Field Detector."""

from typing import List, Optional
from bs4 import BeautifulSoup, Tag
from job_copilot.browser.models import BrowserElementType, BrowserField
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class FormDetector:
    """
    Extracts form elements, labels, types, and context from HTML / DOM.
    """

    @staticmethod
    def detect_fields_from_html(html_content: str) -> List[BrowserField]:
        """Parse HTML string and return structured BrowserField items."""
        soup = BeautifulSoup(html_content, "html.parser")
        fields: List[BrowserField] = []

        # Find all form controls
        form_elements = soup.find_all(["input", "textarea", "select", "button"])
        idx = 0

        for el in form_elements:
            tag_name = el.name.lower()
            input_type = el.get("type", "text").lower() if tag_name == "input" else tag_name

            # Skip hidden inputs or submit buttons from general fields
            if input_type in ["hidden", "password"]:
                # Note: password is DO_NOT_TOUCH/excluded from auto fill
                element_type = BrowserElementType.INPUT_TEXT
            elif tag_name == "input":
                if input_type in ["email"]:
                    element_type = BrowserElementType.INPUT_EMAIL
                elif input_type in ["tel", "phone"]:
                    element_type = BrowserElementType.INPUT_TEL
                elif input_type in ["number"]:
                    element_type = BrowserElementType.INPUT_NUMBER
                elif input_type in ["file"]:
                    element_type = BrowserElementType.INPUT_FILE
                elif input_type in ["radio"]:
                    element_type = BrowserElementType.INPUT_RADIO
                elif input_type in ["checkbox"]:
                    element_type = BrowserElementType.INPUT_CHECKBOX
                elif input_type in ["date"]:
                    element_type = BrowserElementType.INPUT_DATE
                else:
                    element_type = BrowserElementType.INPUT_TEXT
            elif tag_name == "textarea":
                element_type = BrowserElementType.TEXTAREA
            elif tag_name == "select":
                element_type = BrowserElementType.SELECT
            elif tag_name == "button" or (tag_name == "input" and input_type in ["submit", "button"]):
                element_type = BrowserElementType.BUTTON
            else:
                element_type = BrowserElementType.UNKNOWN

            id_attr = el.get("id")
            name_attr = el.get("name")
            field_id = id_attr or name_attr or f"field_{idx}_{tag_name}"

            # Label extraction logic
            label_text = FormDetector._find_label(el, soup)
            placeholder = el.get("placeholder")
            aria_label = el.get("aria-label") or el.get("aria-labelledby")
            autocomplete = el.get("autocomplete")
            required = el.has_attr("required") or el.get("aria-required") == "true"
            current_value = el.get("value")

            # Extract options if select or radio
            options: List[str] = []
            if tag_name == "select":
                for opt in el.find_all("option"):
                    opt_text = opt.get_text(strip=True)
                    if opt_text:
                        options.append(opt_text)

            # Surrounding text context (parent container text)
            context_text = None
            parent = el.parent
            if parent:
                parent_text = parent.get_text(separator=" ", strip=True)
                if len(parent_text) > 0 and len(parent_text) < 300:
                    context_text = parent_text

            selector = f"#{id_attr}" if id_attr else (f"[name='{name_attr}']" if name_attr else None)

            fields.append(
                BrowserField(
                    field_id=field_id,
                    element_type=element_type,
                    name=name_attr,
                    id_attr=id_attr,
                    label=label_text,
                    placeholder=placeholder,
                    aria_label=aria_label,
                    autocomplete=autocomplete,
                    required=required,
                    options=options,
                    visible=True,
                    enabled=not el.has_attr("disabled"),
                    current_value=current_value,
                    context_text=context_text,
                    selector=selector,
                )
            )
            idx += 1

        return fields

    @staticmethod
    def _find_label(element: Tag, soup: BeautifulSoup) -> Optional[str]:
        """Find associated label text using <label for=...>, wrapping <label>, or aria labels."""
        id_attr = element.get("id")
        if id_attr:
            label_tag = soup.find("label", attrs={"for": id_attr})
            if label_tag:
                return label_tag.get_text(strip=True)

        # Check wrapping label
        parent_label = element.find_parent("label")
        if parent_label:
            # Get text excluding the element itself
            return parent_label.get_text(strip=True)

        # Check preceding sibling or close label
        prev = element.find_previous_sibling("label")
        if prev:
            return prev.get_text(strip=True)

        # Check aria-label
        if element.get("aria-label"):
            return element.get("aria-label")

        return None
