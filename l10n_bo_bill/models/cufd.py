from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
from datetime import datetime, timedelta  # Aquí importamos timedelta

_logger = logging.getLogger(__name__)

class CUFD(models.Model):
    _name = 'l10n_bo_bill.cufd'
    _description = 'CUFD'

    external_id = fields.Char(string='External ID', invisible=True)
    codigo = fields.Char(string='Código', required=True)
    codigo_control = fields.Char(string='Código Control', required=True)
    fecha_inicio = fields.Datetime(string='Fecha Inicio', required=True)
    fecha_vigencia = fields.Datetime(string='Fecha Vigencia', required=True)
    vigente = fields.Boolean(string='Vigente', default=True)
    id_punto_venta = fields.Many2one('l10n_bo_bill.punto_venta', string='Punto de Venta', required=True)
    name = fields.Char(string='Name', compute='_compute_name', store=True)

    @api.depends('codigo_control')
    def _compute_name(self):
        for record in self:
            record.name = record.codigo_control

    def _get_api_url(self):
        """Función para obtener la URL de la API activa"""
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)])
        
        if not direccion_apis:
            raise UserError("No se encontró una configuración de la API activa.")
        
        if len(direccion_apis) > 1:
            raise UserError("Hay más de una dirección de API activa. Verifica la configuración.")

        return direccion_apis[0].url  # Retorna la URL activa

    def obtener_cufd_desde_api(self):
        """Función para obtener los CUFD desde la API y sincronizarlos en Odoo"""
        api_url = f"{self._get_api_url()}/codigos/cufd/activo/1"
        
        _logger.info(f"Obteniendo CUFD desde la API: {api_url}")

        try:
            # Realizar la solicitud GET a la API
            response = requests.get(api_url)
            if response.status_code == 200:
                cufds = response.json()
                _logger.info(f"CUFD obtenidos desde la API: {cufds}")

                # Buscar todos los external_id existentes en Odoo
                external_ids = self.search([]).mapped('external_id')

                # Filtrar y crear los CUFD que no están en Odoo
                for cufd in cufds:
                    if str(cufd['id']) not in external_ids:
                        _logger.info(f"Creando CUFD en Odoo: {cufd['codigo']}")

                        # Convertir las fechas de la API al formato esperado por Odoo
                        fecha_inicio = datetime.strptime(cufd['fechaInicio'].split('.')[0], '%Y-%m-%dT%H:%M:%S')
                        fecha_vigencia = datetime.strptime(cufd['fechaVigencia'].split('.')[0], '%Y-%m-%dT%H:%M:%S')

                        # Buscar la relación con Punto de Venta
                        punto_venta = self.env['l10n_bo_bill.punto_venta'].search([('external_id', '=', cufd['puntoVenta']['id'])], limit=1)
                        
                        # Si no se encuentra el punto de venta, se crea
                        if not punto_venta:
                            sucursal_data = cufd['puntoVenta']['sucursal']
                            sucursal = self.env['l10n_bo_bill.sucursal'].search([('external_id', '=', sucursal_data['id'])], limit=1)

                            if not sucursal:
                                _logger.info(f"Creando la sucursal {sucursal_data['nombre']} en Odoo.")
                                sucursal = self.env['l10n_bo_bill.sucursal'].create({
                                    'external_id': sucursal_data['id'],
                                    'codigo': sucursal_data['codigo'],
                                    'nombre': sucursal_data['nombre'],
                                    'departamento': sucursal_data['departamento'],
                                    'municipio': sucursal_data['municipio'],
                                    'direccion': sucursal_data['direccion'],
                                    'telefono': sucursal_data['telefono'],
                                })

                            _logger.info(f"Creando el punto de venta {cufd['puntoVenta']['nombre']} en Odoo.")
                            punto_venta = self.env['l10n_bo_bill.punto_venta'].create({
                                'external_id': cufd['puntoVenta']['id'],
                                'codigo': cufd['puntoVenta']['codigo'],
                                'nombre': cufd['puntoVenta']['nombre'],
                                'id_sucursal': sucursal.id,
                            })

                        # Crear el CUFD en Odoo
                        self.create({
                            'external_id': cufd['id'],
                            'codigo': cufd['codigo'],
                            'codigo_control': cufd['codigoControl'],
                            'fecha_inicio': fecha_inicio,
                            'fecha_vigencia': fecha_vigencia,
                            'vigente': cufd['vigente'],
                            'id_punto_venta': punto_venta.id,
                        })
            else:
                _logger.error(f"Error al obtener CUFD desde la API: {response.status_code} {response.text}")
                raise UserError(f"No se pudieron obtener los CUFD desde la API. Error: {response.status_code} {response.text}")
        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al obtener los CUFD desde la API: {e}")
            raise UserError(f"No se pudo conectar con la API: {e}")
        
        
    def obtener_nuevo_cufd_desde_api(self):
        """Función para obtener el CUFD desde la API y sincronizar en Odoo"""
        api_url = f"{self._get_api_url()}/codigos/obtener-cufd/1/1"  # ID del punto de venta
        _logger.info(f"Obteniendo CUFD desde la API: {api_url}")

        try:
            # Realizar la solicitud POST a la API
            response = requests.post(api_url)
            if response.status_code == 200:
                cufd_data = response.json()
                _logger.info(f"CUFD obtenido desde la API: {cufd_data}")

                # Buscar el Punto de Venta usando el external_id
                punto_venta = self.env['l10n_bo_bill.punto_venta'].search([('external_id', '=', str(cufd_data['idPuntoVenta']))], limit=1)
                
                if not punto_venta:
                    raise UserError(f"No se encontró el Punto de Venta con external_id {cufd_data['idPuntoVenta']} en el sistema.")

                # Desactivar el CUFD vigente actual para el mismo Punto de Venta
                cufd_vigente = self.search([('id_punto_venta', '=', punto_venta.id), ('vigente', '=', True)])
                if cufd_vigente:
                    _logger.info(f"Desactivando CUFD anterior {cufd_vigente.codigo}")
                    cufd_vigente.write({'vigente': False})

                # Convertir las fechas de la API al formato adecuado
                fecha_inicio = datetime.strptime(cufd_data['fechaCreacion'].split('.')[0], '%Y-%m-%dT%H:%M:%S')
                fecha_vigencia = datetime.strptime(cufd_data['fechaVigencia'].split('.')[0], '%Y-%m-%dT%H:%M:%S')

                # Crear el nuevo CUFD en Odoo
                self.create({
                    'codigo': cufd_data['codigo'],
                    'codigo_control': cufd_data['codigoControl'],
                    'fecha_inicio': fecha_inicio,
                    'fecha_vigencia': fecha_vigencia,
                    'vigente': cufd_data['estado'],
                    'id_punto_venta': punto_venta.id,
                    'external_id': cufd_data['idPuntoVenta'],
                })
            else:
                _logger.error(f"Error al obtener el CUFD desde la API: {response.status_code} {response.text}")
                raise UserError(f"Error al obtener el CUFD desde la API. Código: {response.status_code}, Detalles: {response.text}")

        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al obtener el CUFD desde la API: {e}")
            raise UserError(f"Error de conexión con la API: {e}")
        
        
    def verificar_o_crear_cufd(self):
        """Función para verificar si existe un CUFD vigente y si no, crearlo."""
        api_url_get = f"{self._get_api_url()}/codigos/cufd/activo/1"  # Cambiar según el endpoint
        api_url_post = f"{self._get_api_url()}/codigos/obtener-cufd/1"  # Cambiar según el endpoint
        _logger.info(f"Verificando CUFD existente desde la API: {api_url_get}")
        
        # Obtener la fecha de mañana
        fecha_mañana = datetime.now() + timedelta(days=1)

        try:
            # Realizar la solicitud GET a la API
            response_get = requests.get(api_url_get)
            if response_get.status_code == 200:
                cufds = response_get.json()
                _logger.info(f"CUFD obtenidos desde la API: {cufds}")

                # Buscar el CUFD que esté vigente y con fecha de vigencia de mañana
                for cufd in cufds:
                    fecha_vigencia = datetime.strptime(cufd['fechaVigencia'].split('.')[0], '%Y-%m-%dT%H:%M:%S')
                    if cufd['vigente'] and fecha_vigencia.date() == fecha_mañana.date():
                        _logger.info(f"CUFD vigente encontrado con fecha de vigencia: {fecha_vigencia}")
                        return  # Si existe, salir de la función

            else:
                _logger.error(f"Error al obtener CUFD desde la API: {response_get.status_code} {response_get.text}")
                raise UserError(f"Error al obtener CUFD desde la API. Código: {response_get.status_code}, Detalles: {response_get.text}")

        except requests.exceptions.RequestException as e:
            _logger.error(f"Error al verificar el CUFD desde la API: {e}")
            raise UserError(f"No se pudo conectar con la API para verificar el CUFD: {e}")

        # Si no se encontró un CUFD vigente con fecha de vigencia mañana, crearlo con el POST
        _logger.info(f"No se encontró un CUFD vigente con fecha de vigencia para mañana. Creando uno nuevo.")

        try:
            # Realizar la solicitud POST a la API para crear un nuevo CUFD
            response_post = requests.post(api_url_post)
            if response_post.status_code == 200:
                cufd_data = response_post.json()
                _logger.info(f"CUFD creado desde la API: {cufd_data}")

                # Buscar el Punto de Venta usando el external_id
                punto_venta = self.env['l10n_bo_bill.punto_venta'].search([('external_id', '=', str(cufd_data['idPuntoVenta']))], limit=1)
                
                if not punto_venta:
                    raise UserError(f"No se encontró el Punto de Venta con external_id {cufd_data['idPuntoVenta']} en el sistema.")

                # Desactivar el CUFD vigente actual para el mismo Punto de Venta
                cufd_vigente = self.search([('id_punto_venta', '=', punto_venta.id), ('vigente', '=', True)])
                if cufd_vigente:
                    _logger.info(f"Desactivando CUFD anterior {cufd_vigente.codigo}")
                    cufd_vigente.write({'vigente': False})

                # Convertir las fechas de la API al formato adecuado
                fecha_inicio = datetime.strptime(cufd_data['fechaCreacion'].split('.')[0], '%Y-%m-%dT%H:%M:%S')
                fecha_vigencia = datetime.strptime(cufd_data['fechaVigencia'].split('.')[0], '%Y-%m-%dT%H:%M:%S')

                # Crear el nuevo CUFD en Odoo
                self.create({
                    'codigo': cufd_data['codigo'],
                    'codigo_control': cufd_data['codigoControl'],
                    'fecha_inicio': fecha_inicio,
                    'fecha_vigencia': fecha_vigencia,
                    'vigente': cufd_data['estado'],
                    'id_punto_venta': punto_venta.id,
                    'external_id': cufd_data['idPuntoVenta'],
                })
            else:
                _logger.error(f"Error al crear CUFD desde la API: {response_post.status_code} {response_post.text}")
                raise UserError(f"Error al crear CUFD desde la API. Código: {response_post.status_code}, Detalles: {response_post.text}")

        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al crear CUFD desde la API: {e}")
            raise UserError(f"No se pudo conectar con la API para crear el CUFD: {e}")
        
        
    def mensaje_prueba(self):
        messege = 'hola'
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': messege,
                'type': 'success',
                'sticky': False,
            },
        }