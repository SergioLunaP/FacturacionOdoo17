from odoo import models, fields, api
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class PaisOrigen(models.Model):
    _name = 'l10n_bo_bill.pais_origen'
    _description = 'País de Origen'

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

    def obtener_paises_origen_desde_api(self):
        """Función para obtener los países de origen desde la API y sincronizarlos en Odoo"""
        api_url = f"{self._get_api_url()}/parametro/pais-origen"
        
        _logger.info(f"Obteniendo Países de Origen desde la API: {api_url}")

        try:
            # Realizar la solicitud GET a la API
            response = requests.get(api_url)
            if response.status_code == 200:
                paises = response.json()
                _logger.info(f"Países de Origen obtenidos desde la API: {paises}")

                # Buscar todos los external_id existentes en Odoo
                external_ids = self.search([]).mapped('external_id')

                # Filtrar y crear los Países de Origen que no están en Odoo
                for pais in paises:
                    if str(pais['id']) not in external_ids:
                        _logger.info(f"Creando País de Origen en Odoo: {pais['descripcion']}")

                        # Crear el País de Origen en Odoo
                        self.create({
                            'external_id': pais['id'],
                            'codigo_clasificador': pais['codigoClasificador'],
                            'descripcion': pais['descripcion'],
                            'codigo_tipo_parametro': pais['codigoTipoParametro'],
                        })
            else:
                _logger.error(f"Error al obtener Países de Origen desde la API: {response.status_code} {response.text}")
                raise UserError(f"No se pudieron obtener los Países de Origen desde la API. Error: {response.status_code} {response.text}")
        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al obtener los Países de Origen desde la API: {e}")
            raise UserError(f"No se pudo conectar con la API: {e}")
