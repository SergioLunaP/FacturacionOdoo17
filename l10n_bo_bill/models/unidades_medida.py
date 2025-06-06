from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
import time
import threading

_logger = logging.getLogger(__name__)

class UnidadesMedida(models.Model):
    _name = 'l10n_bo_bill.unidades_medida'
    _description = 'Unidades de Medida'

    external_id = fields.Char(string='External ID', invisible=True)
    codigo_clasificador = fields.Char(string='Código Clasificador', required=True)
    descripcion = fields.Char(string='Descripción', required=True)
    codigo_tipo_parametro = fields.Char(string='Código Tipo Parámetro')
    name = fields.Char(string='Nombre', compute='_compute_name', store=True)

    
    @api.depends('descripcion')
    def _compute_name(self):
        for record in self:
            record.name = record.descripcion
            
            
    def _get_api_url(self):
        """Función para obtener la URL de la API activa"""
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)])
        
        if not direccion_apis:
            raise UserError("No se encontró una configuración de la API activa.")
        
        if len(direccion_apis) > 1:
            raise UserError("Hay más de una dirección de API activa. Verifica la configuración.")

        return direccion_apis[0].url  # Retorna la URL activa

    def obtener_unidades_medida_desde_api(self):
        """Función para obtener las unidades de medida desde la API y sincronizarlas en Odoo"""
        api_url = f"{self._get_api_url()}/parametro/unidad-medida"
        
        _logger.info(f"Obteniendo Unidades de Medida desde la API: {api_url}")

        try:
            # Realizar la solicitud GET a la API
            response = requests.get(api_url)
            if response.status_code == 200:
                unidades_medida = response.json()
                _logger.info(f"Unidades de Medida obtenidas desde la API: {unidades_medida}")

                # Buscar todos los external_id existentes en Odoo
                external_ids = self.search([]).mapped('external_id')

                # Filtrar y crear las Unidades de Medida que no están en Odoo
                for unidad in unidades_medida:
                    if str(unidad['id']) not in external_ids:
                        _logger.info(f"Creando Unidad de Medida en Odoo: {unidad['descripcion']}")

                        # Crear la Unidad de Medida en Odoo
                        self.create({
                            'external_id': unidad['id'],
                            'codigo_clasificador': unidad['codigoClasificador'],
                            'descripcion': unidad['descripcion'],
                            'codigo_tipo_parametro': unidad['codigoTipoParametro'],
                        })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _("Warning head"),
                        'type': 'warning',
                        'message': _("This is the detailed warning"),
                        'sticky': True,
                    },
                }
            else:
                _logger.error(f"Error al obtener Unidades de Medida desde la API: {response.status_code} {response.text}")
                raise UserError(f"No se pudieron obtener las Unidades de Medida desde la API. Error: {response.status_code} {response.text}")
        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al obtener las Unidades de Medida desde la API: {e}")
            raise UserError(f"No se pudo conectar con la API: {e}")
        