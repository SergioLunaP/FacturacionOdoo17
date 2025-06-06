from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class CUIS(models.Model):
    _name = 'l10n_bo_bill.cuis'
    _description = 'CUIS'

    external_id = fields.Char(string='External ID', invisible=True)
    codigo = fields.Char(string='Código', required=True)
    fecha_solicitada = fields.Datetime(string='Fecha Solicitada', required=True)
    fecha_vigencia = fields.Datetime(string='Fecha Vigencia', required=True)
    vigente = fields.Boolean(string='Vigente', default=True)
    id_punto_venta = fields.Many2one('l10n_bo_bill.punto_venta', string='Punto de Venta', required=True)
    name = fields.Char(string='Name', compute='_compute_name', store=True)

    @api.depends('codigo')
    def _compute_name(self):
        for record in self:
            record.name = record.codigo

    def _get_api_url(self):
        """Función para obtener la URL de la API activa"""
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)])
        
        if not direccion_apis:
            raise UserError("No se encontró una configuración de la API activa.")
        
        if len(direccion_apis) > 1:
            raise UserError("Hay más de una dirección de API activa. Verifica la configuración.")

        return direccion_apis[0].url  # Retorna la URL activa

    def obtener_cuis_desde_api(self):
        """Función para obtener los CUIS desde la API y sincronizarlos en Odoo"""
        api_url = f"{self._get_api_url()}/codigos/cuis/activo/1"
        
        _logger.info(f"Obteniendo CUIS desde la API: {api_url}")

        try:
            # Realizar la solicitud GET a la API
            response = requests.get(api_url)
            if response.status_code == 200:
                cuis_data = response.json()
                _logger.info(f"CUIS obtenidos desde la API: {cuis_data}")

                # Buscar todos los external_id existentes en Odoo
                external_ids = self.search([]).mapped('external_id')

                # Filtrar y crear los CUIS que no están en Odoo
                for cuis in cuis_data:
                    if str(cuis['id']) not in external_ids:
                        _logger.info(f"Creando CUIS en Odoo: {cuis['codigo']}")

                        # Convertir las fechas de la API al formato esperado por Odoo
                        fecha_solicitada = datetime.strptime(cuis['fechaSolicitada'].split('.')[0], '%Y-%m-%dT%H:%M:%S')
                        fecha_vigencia = datetime.strptime(cuis['fechaVigencia'].split('.')[0], '%Y-%m-%dT%H:%M:%S')

                        # Buscar la relación con Punto de Venta
                        punto_venta = self.env['l10n_bo_bill.punto_venta'].search([('external_id', '=', cuis['puntoVenta']['id'])], limit=1)
                        
                        # Si no se encuentra el punto de venta, se crea junto con su sucursal y empresa
                        if not punto_venta:
                            sucursal_data = cuis['puntoVenta']['sucursal']
                            sucursal = self.env['l10n_bo_bill.sucursal'].search([('external_id', '=', sucursal_data['id'])], limit=1)

                            if not sucursal:
                                # Buscar la empresa relacionada con la sucursal
                                empresa_data = sucursal_data.get('empresa')
                                empresa = self.env['res.company'].search([('external_id', '=', empresa_data['id'])], limit=1)
                                
                                if not empresa:
                                    raise UserError(f"No se encontró la empresa asociada para la sucursal {sucursal_data['nombre']}.")

                                _logger.info(f"Creando la sucursal {sucursal_data['nombre']} en Odoo.")
                                sucursal = self.env['l10n_bo_bill.sucursal'].create({
                                    'external_id': sucursal_data['id'],
                                    'codigo': sucursal_data['codigo'],
                                    'nombre': sucursal_data['nombre'],
                                    'departamento': sucursal_data['departamento'],
                                    'municipio': sucursal_data['municipio'],
                                    'direccion': sucursal_data['direccion'],
                                    'telefono': sucursal_data['telefono'],
                                    'id_empresa': empresa.id  # Asignar la empresa encontrada
                                })

                            _logger.info(f"Creando el punto de venta {cuis['puntoVenta']['nombre']} en Odoo.")
                            punto_venta = self.env['l10n_bo_bill.punto_venta'].create({
                                'external_id': cuis['puntoVenta']['id'],
                                'codigo': cuis['puntoVenta']['codigo'],
                                'nombre': cuis['puntoVenta']['nombre'],
                                'id_sucursal': sucursal.id,
                            })

                        # Crear el CUIS en Odoo
                        self.create({
                            'external_id': cuis['id'],
                            'codigo': cuis['codigo'],
                            'fecha_solicitada': fecha_solicitada,
                            'fecha_vigencia': fecha_vigencia,
                            'vigente': cuis['vigente'],
                            'id_punto_venta': punto_venta.id,
                        })
            else:
                _logger.error(f"Error al obtener CUIS desde la API: {response.status_code} {response.text}")
                raise UserError(f"No se pudieron obtener los CUIS desde la API. Error: {response.status_code} {response.text}")
        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al obtener los CUIS desde la API: {e}")
            raise UserError(f"No se pudo conectar con la API: {e}")
