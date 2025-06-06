from odoo import models, fields, api
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class TiposDocumentoSector(models.Model):
    _name = 'l10n_bo_bill.tipos_documento_sector'
    _description = 'Tipos de Documento de Sector'

    external_id = fields.Char(string='External ID', invisible=True)
    codigo_clasificador = fields.Char(string='Código Clasificador', required=True)
    descripcion = fields.Char(string='Descripción', required=True)
    codigo_tipo_parametro = fields.Char(string='Código Tipo Parámetro')

    def _get_api_url(self):
        """Función para obtener la URL de la API activa"""
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)])
        
        if not direccion_apis:
            raise UserError("No se encontró una configuración de la API activa.")
        
        if len(direccion_apis) > 1:
            raise UserError("Hay más de una dirección de API activa. Verifica la configuración.")

        return direccion_apis[0].url  # Retorna la URL activa

    def obtener_tipos_documento_sector_desde_api(self):
        """Función para obtener los tipos de documento de sector desde la API y sincronizarlos en Odoo"""
        api_url = f"{self._get_api_url()}/parametro/documento-sector"
        
        _logger.info(f"Obteniendo Tipos de Documento de Sector desde la API: {api_url}")

        try:
            # Realizar la solicitud GET a la API
            response = requests.get(api_url)
            if response.status_code == 200:
                tipos_documento_sector = response.json()
                _logger.info(f"Tipos de Documento de Sector obtenidos desde la API: {tipos_documento_sector}")

                # Buscar todos los external_id existentes en Odoo
                external_ids = self.search([]).mapped('external_id')

                # Filtrar y crear los Tipos de Documento de Sector que no están en Odoo
                for tipo in tipos_documento_sector:
                    if str(tipo['id']) not in external_ids:
                        _logger.info(f"Creando Tipo de Documento de Sector en Odoo: {tipo['descripcion']}")

                        # Crear el Tipo de Documento de Sector en Odoo
                        self.create({
                            'external_id': tipo['id'],
                            'codigo_clasificador': tipo['codigoClasificador'],
                            'descripcion': tipo['descripcion'],
                            'codigo_tipo_parametro': tipo['codigoTipoParametro'],
                        })
            else:
                _logger.error(f"Error al obtener Tipos de Documento de Sector desde la API: {response.status_code} {response.text}")
                raise UserError(f"No se pudieron obtener los Tipos de Documento de Sector desde la API. Error: {response.status_code} {response.text}")
        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al obtener los Tipos de Documento de Sector desde la API: {e}")
            raise UserError(f"No se pudo conectar con la API: {e}")
