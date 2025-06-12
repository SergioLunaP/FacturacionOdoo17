from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class Cufd(models.Model):
    _name = 'l10n_bo_bill.cufd'
    _description = 'CUFD'

    codigo = fields.Char(string='Código CUFD')
    codigo_control = fields.Char(string='Código Control')
    fecha_inicio = fields.Datetime(string='Fecha Creación')
    fecha_vigencia = fields.Datetime(string='Fecha Vigencia')
    vigente = fields.Boolean(string='Vigente', default=True)

    def _get_api_url(self):
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)], limit=1)
        if not direccion_apis:
            raise UserError("No se encontró una configuración de la API activa.")
        if len(direccion_apis) > 1:
            raise UserError("Hay más de una dirección de API activa.")
        return direccion_apis.url

    def obtener_cufd(self):
        for record in self:
            url = f"{record._get_api_url()}/codigos/obtener-cufd/1/1"
            try:
                response = requests.post(url, timeout=10)
                response.raise_for_status()
                data = response.json()

                if not data.get("estado"):
                    raise UserError(f"Error en la API: {data.get('mensajeError') or 'Error desconocido'}")

                # Marcar anteriores como no vigentes
                self.env['l10n_bo_bill.cufd'].search([
                    ('vigente', '=', True)
                ]).write({'vigente': False})

                # Convertir fecha ISO a datetime de Python
                fecha_inicio = fields.Datetime.from_string(data.get('fechaCreacion').replace("T", " ")[:19])
                fecha_vigencia = fields.Datetime.from_string(data.get('fechaVigencia').replace("T", " ")[:19])

                self.create({
                    'codigo': data.get('codigo'),
                    'codigo_control': data.get('codigoControl'),
                    'fecha_inicio': fecha_inicio,
                    'fecha_vigencia': fecha_vigencia,
                    'vigente': True,
                })

                _logger.info(f"CUFD creado correctamente: {data.get('codigo')}")

            except requests.exceptions.RequestException as e:
                _logger.error(f"Error al obtener CUFD: {e}")
                raise UserError(f"No se pudo obtener el CUFD: {e}")



    @api.model
    def cron_obtener_cufd_diario(self):
        try:
            url = f"{self._get_api_url()}/codigos/obtener-cufd/1/1"

            response = requests.post(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("estado"):
                self.search([('vigente', '=', True)]).write({'vigente': False})

                self.create({
                    'codigo': data.get('codigo'),
                    'codigo_control': data.get('codigoControl'),
                    'fecha_inicio': data.get('fechaCreacion'),
                    'fecha_vigencia': data.get('fechaVigencia'),
                    'vigente': True,
                })
                _logger.info("CUFD generado automáticamente desde el cron.")
            else:
                _logger.warning(f"Error al obtener CUFD desde cron: {data.get('mensajeError')}")

        except requests.exceptions.RequestException as e:
            _logger.error(f"Error al obtener CUFD en cron: {e}")
