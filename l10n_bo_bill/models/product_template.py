from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
import json

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    # Campos antiguos

    # Nuevos campos
    external_id = fields.Char(string='ID externo', readonly=True)
    product_code = fields.Selection(selection='_get_product_codes', string="Código de Producto", required=True, help="Selecciona un código de producto desde la API")
    unit_measure_code = fields.Selection(selection='_get_unit_measures', string="Unidad de Medida", required=True, help="Selecciona una unidad de medida desde la API")

    def _get_api_url(self):
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)], limit=1)

        if not direccion_apis:
            raise UserError("No se encontró una configuración de la API activa.")
        
        if len(direccion_apis) > 1:
            raise UserError("Hay más de una dirección de API activa. Por favor, verifica la configuración.")

        return direccion_apis.url

    @api.model
    def _get_product_codes(self):
        api_url = self._get_api_url()
        url = f"{api_url}/productos"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            productos = response.json()

            if not isinstance(productos, list):
                raise UserError("La API no devolvió una lista válida de productos.")

            seen = set()
            product_list = []
            for p in productos:
                codigo = str(p.get("codigoProducto"))
                if codigo and codigo not in seen:
                    seen.add(codigo)
                    descripcion = p.get('descripcionProducto', 'Sin descripción')
                    product_list.append((codigo, f"{codigo} - {descripcion}"))

            return product_list

        except requests.exceptions.RequestException as e:
            _logger.error(f"Error al obtener productos de la API: {e}")
            return []

    @api.model
    def _get_unit_measures(self):
        api_url = self._get_api_url()
        url = f"{api_url}/parametro/unidad-medida"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            unidades = response.json()

            if not isinstance(unidades, list):
                raise UserError("La API no devolvió una lista válida de unidades de medida.")

            seen = set()
            units_list = []
            for u in unidades:
                codigo = str(u.get("codigoClasificador"))
                if codigo and codigo not in seen:
                    seen.add(codigo)
                    descripcion = u.get('descripcion', 'Sin descripción')
                    units_list.append((codigo, f"{codigo} - {descripcion}"))

            return units_list

        except requests.exceptions.RequestException as e:
            _logger.error(f"Error al obtener unidades de medida de la API: {e}")
            return []

    @api.model
    def create(self, vals):
        record = super(ProductTemplate, self).create(vals)

        required_fields = ["default_code", "name", "list_price", "unit_measure_code", "product_code"]
        if not all(vals.get(field) for field in required_fields):
            raise UserError("Faltan datos requeridos para enviar el producto a la API.")

        payload = {
            "codigo": vals.get("default_code"),
            "descripcion": vals.get("name"),
            "unidadMedida": int(vals.get("unit_measure_code")),
            "precioUnitario": float(vals.get("list_price")),
            "codigoProductoSin": int(vals.get("product_code"))
        }

        api_url = self._get_api_url()
        url = f"{api_url}/item/crear-item"

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            response_data = response.json()

            if "id" in response_data:
                external_id = response_data["id"]
                query = """
                    UPDATE product_template
                    SET external_id = %s
                    WHERE id = %s;
                """
                self.env.cr.execute(query, (external_id, record.id))
            else:
                _logger.error("La API no devolvió un ID válido.")

        except requests.exceptions.RequestException as e:
            _logger.error(f"Error al enviar producto a la API: {e}")
            raise UserError(f"Error al enviar producto a la API: {e}")

        return record
    
    def write(self, vals):
        result = super(ProductTemplate, self).write(vals)

        for record in self:
            if not record.external_id:
                continue  # Si no hay ID externo, no se puede actualizar en la API

            payload = {
                "codigo": record.default_code,
                "descripcion": record.name,
                "unidadMedida": int(record.unit_measure_code),
                "precioUnitario": float(record.list_price),
                "codigoProductoSin": int(record.product_code)
            }

            api_url = record._get_api_url()
            url = f"{api_url}/item/actualizar-item/{record.external_id}"

            try:
                _logger.info(f"🔁 Actualizando producto en API con ID {record.external_id}")
                _logger.info(f"📤 Payload enviado: {json.dumps(payload, indent=2)}")
                response = requests.put(url, json=payload, timeout=10)
                response.raise_for_status()
                data = response.json()
                _logger.info(f"✅ Producto actualizado en API: {data}")
            except requests.exceptions.RequestException as e:
                _logger.error(f"❌ Error al actualizar producto {record.name} en la API: {e}")
                raise UserError(f"Error al actualizar producto en la API: {e}")

        return result

