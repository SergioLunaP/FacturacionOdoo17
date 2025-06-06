import requests
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class Sucursal(models.Model):
    _name = 'l10n_bo_bill.sucursal'
    _description = 'Sucursal'
    
    external_id = fields.Char(string='External ID', invisible=True)
    codigo = fields.Char(string='Código', required=True)
    departamento = fields.Char(string='Departamento', required=True)
    direccion = fields.Char(string='Dirección', required=True)
    municipio = fields.Char(string='Municipio', required=True)
    nombre = fields.Char(string='Nombre', required=True)
    telefono = fields.Char(string='Teléfono')
    id_empresa = fields.Many2one('res.company', string='Empresa', required=True)  # Convertido en relación con res.company

    puntos_venta_ids = fields.One2many('l10n_bo_bill.punto_venta', 'id_sucursal', string='Puntos de Venta')

    # Campo Name que muestra Nombre y Departamento
    name = fields.Char(string='Name', compute='_compute_name', store=True)

    @api.depends('nombre', 'departamento')
    def _compute_name(self):
        for record in self:
            # El campo name muestra el nombre y el departamento concatenados
            record.name = f"{record.nombre} - {record.departamento}" if record.nombre and record.departamento else record.nombre
    
    def _get_api_url(self):
        """Función para obtener la URL de la API activa"""
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)])
        
        if not direccion_apis:
            raise UserError("No se encontró una configuración de la API activa.")
        
        if len(direccion_apis) > 1:
            raise UserError("Hay más de una dirección de API activa. Por favor, verifica la configuración.")

        _logger.info("URL de la API activa obtenida: %s", direccion_apis[0].url)
        return direccion_apis[0].url
    
    @api.model
    def create(self, vals):
        record = super(Sucursal, self).create(vals)
        record._sync_with_api('POST')
        return record

    def _sync_with_api(self, method):
        """Función para sincronizar la sucursal con la API"""
        url = f"{self._get_api_url()}/sucursales"
        headers = {'Content-Type': 'application/json'}
        
        payload = {
            'codigo': self.codigo,
            'nombre': self.nombre,
            'departamento': self.departamento,
            'municipio': self.municipio,
            'direccion': self.direccion,
            'telefono': self.telefono,
            'empresa': {
                'id': self.id_empresa.external_id
            }
        }

        try:
            if method == 'POST':
                response = requests.post(url, json=payload, headers=headers)
            else:
                raise UserError("Método no soportado para sincronización.")

            _logger.info("Respuesta de la API al sincronizar sucursal: Código de estado %s, Respuesta: %s", response.status_code, response.text)

            if response.status_code == 200 or response.status_code == 201:
                data = response.json()
                self.external_id = data.get('id')
                _logger.info("Sincronización exitosa. External ID recibido: %s", data.get('id'))
            else:
                error_msg = _("Error al sincronizar la sucursal con la API. Código de estado: %s. Respuesta: %s") % (response.status_code, response.text)
                _logger.error(error_msg)
                raise UserError(error_msg)

        except requests.exceptions.RequestException as e:
            _logger.exception("No se pudo conectar a la API de sucursales.")
            raise UserError(_("No se pudo conectar a la API de sucursales: %s") % str(e))
        
        
    def update_sucursal_in_api(self):
        """Función para sincronizar la edición de la sucursal con la API"""
        url = f"{self._get_api_url()}/sucursales/{self.external_id}"
        headers = {'Content-Type': 'application/json'}
        
        payload = {
            'codigo': self.codigo,
            'nombre': self.nombre,
            'departamento': self.departamento,
            'municipio': self.municipio,
            'direccion': self.direccion,
            'telefono': self.telefono,
            'empresa': {
                'id': self.id_empresa.external_id
            }
        }

        try:
            response = requests.put(url, json=payload, headers=headers)
            _logger.info("Respuesta de la API al actualizar sucursal: Código de estado %s, Respuesta: %s", response.status_code, response.text)

            if response.status_code != 200:
                error_msg = _("Error al sincronizar la edición de la sucursal con la API. Código de estado: %s. Respuesta: %s") % (response.status_code, response.text)
                _logger.error(error_msg)
                raise UserError(error_msg)

        except requests.exceptions.RequestException as e:
            _logger.exception("No se pudo conectar a la API de sucursales.")
            raise UserError(_("No se pudo conectar a la API de sucursales: %s") % str(e))
        
    def write(self, vals):
        res = super(Sucursal, self).write(vals)
        for record in self:
            if record.external_id:
                record.update_sucursal_in_api()  # Llamada a la función de sincronización con la API para ediciones
        return res
    
    
    def action_sync_puntos_venta(self):
        """Sincronizar puntos de venta relacionados con la sucursal desde la API"""
        api_url = f"{self._get_api_url()}/operaciones/punto-venta/lista-bd"
        headers = {'Content-Type': 'application/json'}
        
        try:
            response = requests.get(api_url, headers=headers)
            response_data = response.json()
            _logger.info(f"Respuesta de la API para sincronización de puntos de venta: {response_data}")

            if response.status_code == 200:
                for punto_data in response_data:
                    # Filtrar solo los puntos de venta con sucursal que coincida con `external_id` de la sucursal actual y que estén vigentes
                    if str(punto_data['sucursal']['id']) == self.external_id and punto_data.get('vigente'):
                        
                        # Manejo de `tipo` nulo y búsqueda del tipo de punto de venta
                        tipo_punto_venta = None
                        if punto_data['tipo'] is not None:
                            tipo_punto_venta = self.env['l10n_bo_bill.tipos_punto_venta'].search([('codigo_clasificador', '=', punto_data['tipo'])], limit=1)
                        
                        if not tipo_punto_venta and punto_data['tipo'] is not None:
                            _logger.error(f"Tipo de punto de venta con codigo_clasificador {punto_data['tipo']} no encontrado. No se puede crear el Punto de Venta {punto_data['nombre']}.")
                            continue  # Saltar a la siguiente iteración si el tipo no se encuentra

                        # Verificar si el punto de venta ya existe en la base de datos
                        self.env.cr.execute("SELECT id FROM l10n_bo_bill_punto_venta WHERE external_id = %s", (str(punto_data['id']),))
                        existing_punto_venta = self.env.cr.fetchone()

                        if existing_punto_venta:
                            # Actualizar el punto de venta existente
                            self.env.cr.execute("""
                                UPDATE l10n_bo_bill_punto_venta
                                SET codigo = %s,
                                    nombre = %s,
                                    descripcion = %s,
                                    tipo = %s,
                                    id_sucursal = %s
                                WHERE id = %s
                            """, (
                                punto_data['codigo'],
                                punto_data['nombre'],
                                punto_data.get('descripcion', ''),
                                tipo_punto_venta.id if tipo_punto_venta else None,  # Asignar el `id` del tipo encontrado o None
                                self.id,
                                existing_punto_venta[0]
                            ))
                            _logger.info(f"Punto de Venta actualizado: {punto_data['nombre']}")
                        else:
                            # Crear el punto de venta nuevo
                            self.env.cr.execute("""
                                INSERT INTO l10n_bo_bill_punto_venta (external_id, codigo, nombre, descripcion, tipo, id_sucursal)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """, (
                                punto_data['id'],
                                punto_data['codigo'],
                                punto_data['nombre'],
                                punto_data.get('descripcion', ''),
                                tipo_punto_venta.id if tipo_punto_venta else None,  # Asignar el `id` del tipo encontrado o None
                                self.id
                            ))
                            _logger.info(f"Punto de Venta creado: {punto_data['nombre']}")
                self.env.cr.commit()  # Confirmar los cambios en la base de datos
            else:
                _logger.error(f"Error al obtener puntos de venta desde la API: {response.status_code} {response.text}")
                raise UserError("Error al obtener puntos de venta desde la API.")

        except requests.exceptions.RequestException as e:
            _logger.exception("Error de conexión con la API al sincronizar puntos de venta.")
            raise UserError("No se pudo conectar con la API para sincronizar puntos de venta.")