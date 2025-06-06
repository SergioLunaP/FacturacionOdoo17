from odoo import models, fields, api
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class MetodoPago(models.Model):
    _inherit = 'payment.method'  # Se extiende el modelo de métodos de pago nativo de Odoo

    external_id = fields.Char(string='External ID', invisible=True)
    codigo_clasificador = fields.Char(string='Código Clasificador', required=True)
    name = fields.Char(string='Descripción', required=True)
    code = fields.Char(string='Código Tipo Parámetro')  # Usamos el campo code existente para 'codigoTipoParametro'

    def _get_api_url(self):
        """Función para obtener la URL de la API activa"""
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)])
        
        if not direccion_apis:
            raise UserError("No se encontró una configuración de la API activa.")
        
        if len(direccion_apis) > 1:
            raise UserError("Hay más de una dirección de API activa. Verifica la configuración.")

        return direccion_apis[0].url  # Retorna la URL activa

    def obtener_metodos_pago_desde_api(self):
        """Función para obtener los métodos de pago desde la API y sincronizarlos en Odoo"""
        api_url = f"{self._get_api_url()}/parametro/metodo-pago"
        
        _logger.info(f"Obteniendo Métodos de Pago desde la API: {api_url}")

        try:
            # Realizar la solicitud GET a la API
            response = requests.get(api_url)
            if response.status_code == 200:
                metodos_pago = response.json()
                _logger.info(f"Métodos de Pago obtenidos desde la API: {metodos_pago}")

                # Buscar todos los external_id existentes en Odoo
                external_ids = self.search([]).mapped('external_id')

                # Filtrar y crear los métodos de pago que no están en Odoo
                for metodo in metodos_pago:
                    if str(metodo['id']) not in external_ids:
                        _logger.info(f"Creando Método de Pago en Odoo: {metodo['descripcion']}")
                        
                        # Crear el Método de Pago en Odoo
                        self.create({
                            'external_id': metodo['id'],
                            'codigo_clasificador': metodo['codigoClasificador'],
                            'name': metodo['descripcion'],
                            'code': metodo['codigoTipoParametro'],  # Guardar 'codigoTipoParametro' en el campo 'code'
                        })
            else:
                _logger.error(f"Error al obtener Métodos de Pago desde la API: {response.status_code} {response.text}")
                raise UserError(f"No se pudieron obtener los Métodos de Pago desde la API. Error: {response.status_code} {response.text}")
        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al obtener los Métodos de Pago desde la API: {e}")
            raise UserError(f"No se pudo conectar con la API: {e}")
