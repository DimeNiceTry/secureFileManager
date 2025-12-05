import json
import xml.etree.ElementTree as ET
from xml.etree.ElementTree import XMLParser
from typing import Dict, Any, Union
from loguru import logger

from ..config import get_settings

class JsonXmlService:

    def __init__(self):
        self.settings = get_settings()
        self.max_json_size = 10 * 1024 * 1024
        self.max_xml_size = 10 * 1024 * 1024
        self.max_json_depth = 100
        self.max_xml_elements = 10000

    def safe_load_json(self, content: str) -> Dict[str, Any]:

        try:
            content_size = len(content.encode('utf-8'))
            if content_size > self.max_json_size:
                raise ValueError(f"JSON content too large: {content_size} bytes (max: {self.max_json_size})")

            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON format: {e}")

            max_depth = self._get_json_depth(data)
            if max_depth > self.max_json_depth:
                raise ValueError(f"JSON nesting too deep: {max_depth} levels (max: {self.max_json_depth})")

            self._validate_json_security(data)

            logger.info(f"Successfully loaded JSON data (size: {content_size} bytes, depth: {max_depth})")
            return data

        except Exception as e:
            logger.error(f"Failed to load JSON: {e}")
            raise

    def safe_dump_json(self, data: Dict[str, Any], indent: int = 2) -> str:

        try:

            max_depth = self._get_json_depth(data)
            if max_depth > self.max_json_depth:
                raise ValueError(f"Data nesting too deep: {max_depth} levels (max: {self.max_json_depth})")

            json_content = json.dumps(
                data,
                ensure_ascii=False,
                indent=indent,
                separators=(',', ': '),
                sort_keys=True
            )

            content_size = len(json_content.encode('utf-8'))
            if content_size > self.max_json_size:
                raise ValueError(f"Serialized JSON too large: {content_size} bytes (max: {self.max_json_size})")

            logger.info(f"Successfully serialized JSON data (size: {content_size} bytes)")
            return json_content

        except Exception as e:
            logger.error(f"Failed to serialize JSON: {e}")
            raise

    def safe_load_xml(self, content: str) -> Dict[str, Any]:

        try:

            content_size = len(content.encode('utf-8'))
            if content_size > self.max_xml_size:
                raise ValueError(f"XML content too large: {content_size} bytes (max: {self.max_xml_size})")

            parser = self._create_secure_xml_parser()

            try:

                root = ET.fromstring(content, parser=parser)
            except ET.ParseError as e:
                raise ValueError(f"Invalid XML format: {e}")

            element_count = len(list(root.iter()))
            if element_count > self.max_xml_elements:
                raise ValueError(f"Too many XML elements: {element_count} (max: {self.max_xml_elements})")

            xml_dict = self._xml_to_dict(root)

            self._validate_xml_security(xml_dict)

            logger.info(f"Successfully loaded XML data (size: {content_size} bytes, elements: {element_count})")
            return xml_dict

        except Exception as e:
            logger.error(f"Failed to load XML: {e}")
            raise

    def safe_dump_xml(self, data: Dict[str, Any], root_name: str = "root") -> str:

        try:

            root = ET.Element(root_name)

            self._dict_to_xml(data, root)

            element_count = len(list(root.iter()))
            if element_count > self.max_xml_elements:
                raise ValueError(f"Too many XML elements: {element_count} (max: {self.max_xml_elements})")

            xml_content = ET.tostring(root, encoding='unicode', method='xml')

            formatted_xml = f'<?xml version="1.0" encoding="utf-8"?>\n{xml_content}'

            content_size = len(formatted_xml.encode('utf-8'))
            if content_size > self.max_xml_size:
                raise ValueError(f"Serialized XML too large: {content_size} bytes (max: {self.max_xml_size})")

            logger.info(f"Successfully serialized XML data (size: {content_size} bytes, elements: {element_count})")
            return formatted_xml

        except Exception as e:
            logger.error(f"Failed to serialize XML: {e}")
            raise

    def _get_json_depth(self, obj: Any, depth: int = 0) -> int:

        if depth > self.max_json_depth:
            return depth

        if isinstance(obj, dict):
            return max([self._get_json_depth(value, depth + 1) for value in obj.values()] + [depth])
        elif isinstance(obj, list):
            return max([self._get_json_depth(item, depth + 1) for item in obj] + [depth])
        else:
            return depth

    def _validate_json_security(self, data: Any) -> None:

        def check_value(obj):
            if isinstance(obj, str):

                suspicious_patterns = [
                    '<script', '</script>', 'javascript:', 'data:',
                    'eval(', 'setTimeout(', 'setInterval(',
                    '__import__', 'exec(', 'eval('
                ]
                obj_lower = obj.lower()
                for pattern in suspicious_patterns:
                    if pattern in obj_lower:
                        logger.warning(f"Suspicious pattern detected in JSON: {pattern}")
            elif isinstance(obj, dict):
                for value in obj.values():
                    check_value(value)
            elif isinstance(obj, list):
                for item in obj:
                    check_value(item)

        check_value(data)

    def _create_secure_xml_parser(self) -> XMLParser:

        class SecureXMLParser(XMLParser):
            def __init__(self):
                super().__init__()

                self.parser.DefaultHandler = self._default_handler
                self.parser.ExternalEntityRefHandler = self._external_entity_handler
                self.parser.EntityDeclHandler = self._entity_decl_handler

            def _default_handler(self, data):

                pass

            def _external_entity_handler(self, context, base, sysId, notationName):

                raise ValueError("External entity references are not allowed")

            def _entity_decl_handler(self, entityName, is_parameter_entity, value, base, systemId, publicId, notationName):

                if systemId or publicId:
                    raise ValueError("External entity declarations are not allowed")

        return SecureXMLParser()

    def _validate_xml_security(self, data: Dict[str, Any]) -> None:

        self._validate_json_security(data)

    def _xml_to_dict(self, element: ET.Element) -> Dict[str, Any]:

        result = {}

        if element.attrib:
            result['@attributes'] = element.attrib

        if element.text and element.text.strip():
            if len(element) == 0:

                return element.text.strip()
            else:
                result['#text'] = element.text.strip()

        for child in element:
            child_data = self._xml_to_dict(child)

            if child.tag in result:

                if not isinstance(result[child.tag], list):
                    result[child.tag] = [result[child.tag]]
                result[child.tag].append(child_data)
            else:
                result[child.tag] = child_data

        return result if result else None

    def _dict_to_xml(self, data: Any, parent: ET.Element) -> None:

        if isinstance(data, dict):
            for key, value in data.items():
                if key == '@attributes':

                    if isinstance(value, dict):
                        for attr_name, attr_value in value.items():
                            parent.set(attr_name, str(attr_value))
                elif key == '#text':

                    parent.text = str(value)
                else:

                    if isinstance(value, list):
                        for item in value:
                            child = ET.SubElement(parent, key)
                            self._dict_to_xml(item, child)
                    else:
                        child = ET.SubElement(parent, key)
                        self._dict_to_xml(value, child)
        else:

            parent.text = str(data) if data is not None else ""

    def validate_file_format(self, filename: str, content: str) -> bool:

        try:
            if filename.lower().endswith('.json'):
                self.safe_load_json(content)
                return True
            elif filename.lower().endswith('.xml'):
                self.safe_load_xml(content)
                return True
            else:

                return True

        except Exception as e:
            logger.warning(f"File format validation failed for {filename}: {e}")
            return False