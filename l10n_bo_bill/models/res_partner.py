from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = 'res.partner'

    external_id = fields.Char(string='ID externo', readonly=True)
    complemento = fields.Char(string='Complemento')
    codigo_cliente = fields.Char(string='Código Cliente')

    tipo_documento_identidad = fields.Selection(
        selection='_get_tipo_documento_identidad',
        string="Tipo de Documento",
        required=True,
        help="Selecciona el tipo de documento desde la API"
    )

    def _get_api_url(self):
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)])
        if not direccion_apis:
            raise UserError("No se encontró una configuración de la API activa.")
        if len(direccion_apis) > 1:
            raise UserError("Hay más de una dirección de API activa. Verifique configuración.")
        return direccion_apis[0].url

    @api.model
    def _get_tipo_documento_identidad(self):
        """Obtiene las opciones de tipo de documento desde la API"""
        api_url = self._get_api_url()
        url = f"{api_url}/parametro/identidad"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            tipos = response.json()

            if not isinstance(tipos, list):
                raise UserError("La API no devolvió una lista válida de tipos de documento.")

            return [
                (str(t.get("codigoClasificador")), f"{t.get('codigoClasificador')} - {t.get('descripcion', 'Sin descripción')}")
                for t in tipos if t.get("codigoClasificador")
            ]

        except requests.exceptions.RequestException as e:
            _logger.error(f"Error al obtener tipos de documento desde la API: {e}")
            return []

    @api.model
    def create(self, vals):
        record = super(ResPartner, self).create(vals)

        required_fields = ["name", "vat", "codigo_cliente", "email", "tipo_documento_identidad"]
        missing_fields = [
            self._fields[field].string for field in required_fields if not vals.get(field)
        ]

        if missing_fields:
            raise UserError(
                _("Faltan los siguientes campos requeridos para enviar el cliente a la API:\n- %s") %
                "\n- ".join(missing_fields)
            )

        payload = {
            "nombreRazonSocial": vals.get("name"),
            "codigoTipoDocumentoIdentidad": int(vals.get("tipo_documento_identidad")),
            "numeroDocumento": vals.get("vat"),
            "complemento": vals.get("complemento", ""),
            "codigoCliente": vals.get("codigo_cliente"),
            "email": vals.get("email")
        }

        api_url = self._get_api_url()
        url = f"{api_url}/api/clientes"

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            response_data = response.json()

            if "id" in response_data:
                external_id = response_data["id"]
                self.env.cr.execute("""
                    UPDATE res_partner
                    SET external_id = %s
                    WHERE id = %s;
                """, (external_id, record.id))
            else:
                _logger.error("La API no devolvió un ID válido para el cliente.")

        except requests.exceptions.RequestException as e:
            _logger.error(f"Error al enviar cliente a la API: {e}")
            raise UserError(f"No se pudo sincronizar el cliente con la API: {e}")

        return record

    
    def write(self, vals):
        result = super(ResPartner, self).write(vals)

        for record in self:
            if not record.external_id:
                continue  # Solo actualiza si ya fue sincronizado

            payload = {
                "nombreRazonSocial": vals.get("name", record.name),
                "codigoTipoDocumentoIdentidad": int(vals.get("tipo_documento_identidad", record.tipo_documento_identidad)),
                "numeroDocumento": vals.get("vat", record.vat),
                "complemento": vals.get("complemento", record.complemento or ""),
                "codigoCliente": vals.get("codigo_cliente", record.codigo_cliente),
                "email": vals.get("email", record.email)
            }

            api_url = self._get_api_url()
            url = f"{api_url}/api/clientes/{record.external_id}"

            try:
                response = requests.put(url, json=payload, timeout=10)
                response.raise_for_status()
                _logger.info(f"✅ Cliente actualizado en la API: ID {record.external_id}")
            except requests.exceptions.RequestException as e:
                _logger.error(f"❌ Error al actualizar cliente en la API: {e}")
                raise UserError(f"No se pudo actualizar el cliente en la API: {e}")

        return result

    def unlink(self):
        for record in self:
            if record.external_id:
                api_url = self._get_api_url()
                url = f"{api_url}/api/clientes/{record.external_id}"

                try:
                    response = requests.delete(url, timeout=10)
                    if response.status_code not in (200, 204):
                        raise UserError(f"No se pudo eliminar el cliente en la API: {response.text}")
                    _logger.info(f"🗑️ Cliente eliminado en la API: ID {record.external_id}")
                except requests.exceptions.RequestException as e:
                    _logger.error(f"❌ Error al eliminar cliente en la API: {e}")
                    raise UserError(f"No se pudo eliminar el cliente en la API: {e}")

        return super(ResPartner, self).unlink()
