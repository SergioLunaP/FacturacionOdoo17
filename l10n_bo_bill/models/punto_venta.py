import requests
import threading
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime

_logger = logging.getLogger(__name__)

class PuntoVenta(models.Model):
    _name = 'l10n_bo_bill.punto_venta'
    _description = 'Punto de Venta'

    external_id = fields.Char(string='External ID', invisible=True)
    codigo = fields.Char(string='Código', required=True)
    nombre = fields.Char(string='Nombre', required=True)
    id_sucursal = fields.Many2one('l10n_bo_bill.sucursal', string='Sucursal')
    descripcion = fields.Text(string='Descripción')
    tipo = fields.Many2one('l10n_bo_bill.tipos_punto_venta', string='Tipo')

    cufd_ids = fields.One2many('l10n_bo_bill.cufd', 'id_punto_venta', string='CUFD')
    cuis_activo_id = fields.Many2one('l10n_bo_bill.cuis', string='CUIS Activo', compute='_compute_cuis_activo')
    name = fields.Char(string='Name', compute='_compute_name', store=True)
    punto_venta_principal = fields.Boolean(string='Punto de Venta Principal', default=False)

    contingencia = fields.Boolean(string="Contingencia", default=False)
    id_evento = fields.Char(string='Id del Evento', invisible=True)
    


    @api.depends('codigo', 'nombre')
    def _compute_name(self):
        for record in self:
            record.name = f"{record.codigo} - {record.nombre}" if record.codigo and record.nombre else record.nombre

    def _compute_cuis_activo(self):
        for record in self:
            cuis_activo = self.env['l10n_bo_bill.cuis'].search([('id_punto_venta', '=', record.id), ('vigente', '=', True)], limit=1)
            record.cuis_activo_id = cuis_activo if cuis_activo else False

    @api.model
    def create(self, vals):
        # Crear el registro en Odoo primero
        punto_venta = super(PuntoVenta, self).create(vals)
        
        # Preparar los datos para la API
        payload = {
            "codigoTipoPuntoVenta": punto_venta.tipo.id,
            "nombre": punto_venta.nombre,
            "descripcion": punto_venta.descripcion or "",
            "codigoSucursal": punto_venta.id_sucursal.codigo,
            "idEmpresa": punto_venta.id_sucursal.id_empresa.external_id,
        }
        
        _logger.info(f"Preparando para enviar a la API: {payload}")

        # Obtener la URL de la API
        api_url = f"{self._get_api_url()}/operaciones/punto-venta/registrar"
        headers = {'Content-Type': 'application/json'}

        try:
            # Hacer la solicitud POST a la API
            _logger.info(f"Enviando solicitud POST a la API en {api_url}")
            response = requests.post(api_url, json=payload, headers=headers)
            
            _logger.info(f"Respuesta de la API - Código de estado: {response.status_code}")
            _logger.info(f"Respuesta de la API - Contenido: {response.text}")
            
            response_data = response.json()

            if response.status_code == 200 and response_data.get('transaccion', False):
                # Guardar el `codigoPuntoVenta` en el campo `external_id`
                punto_venta.external_id = response_data.get('codigoPuntoVenta')
                _logger.info(f"Punto de Venta creado en la API con external_id: {punto_venta.external_id}")
            else:
                _logger.error(f"Error al crear Punto de Venta en la API: {response_data}")
                raise UserError("No se pudo crear el Punto de Venta en la API.")
        
        except requests.exceptions.RequestException as e:
            _logger.exception("Error al conectar con la API para crear el Punto de Venta.")
            raise UserError("Error de conexión con la API para crear el Punto de Venta.")

        return punto_venta

    def _get_api_url(self):
        """Función para obtener la URL de la API activa"""
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)])
        
        if not direccion_apis:
            raise UserError("No se encontró una configuración de la API activa.")
        
        if len(direccion_apis) > 1:
            raise UserError("Hay más de una dirección de API activa. Por favor, verifica la configuración.")

        _logger.info(f"URL de la API activa obtenida: {direccion_apis[0].url}")
        return direccion_apis[0].url

    def activar_contingencia(self):
        """Activa el modo de contingencia y programa su desactivación."""
        # Activa el modo de contingencia
        self.contingencia = True

        # Programar el cron job para desactivarlo después de un tiempo
        self.env['ir.cron'].create({
            'name': 'Desactivar contingencia en Punto de Venta',
            'model_id': self.env.ref('l10n_bo_bill.model_l10n_bo_bill_punto_venta').id,
            'state': 'code',
            'code': 'model.desactivar_contingencia_programado()',
            'interval_number': 15,  # Ejecutar una vez cada 1 minuto
            'interval_type': 'minutes',  # Cambiar 'seconds' a 'minutes'
            'numbercall': 1,  # Llamarlo solo una vez
        })

    @api.model
    def desactivar_contingencia_programado(self):
        """Desactiva el modo de contingencia en puntos de venta."""
        puntos_venta = self.search([('contingencia', '=', True)])
        puntos_venta.write({'contingencia': False})
        
        
        
    def obtener_nuevo_cufd_desde_api(self):
        """Función para obtener un nuevo CUFD desde la API y sincronizar en Odoo desde Punto de Venta"""
        
        # Verificamos que el Punto de Venta y la Sucursal tengan un external_id
        if not self.external_id or not self.id_sucursal.external_id:
            raise UserError("Falta el 'external_id' en el Punto de Venta o en la Sucursal.")

        # Construimos la URL del endpoint con los external_ids de Punto de Venta y Sucursal
        api_url = f"{self._get_api_url()}/codigos/obtener-cufd/{self.external_id}/{self.id_sucursal.external_id}"
        
        _logger.info(f"Obteniendo nuevo CUFD desde la API: {api_url}")

        try:
            # Realizar la solicitud POST a la API
            response = requests.post(api_url)
            if response.status_code == 200:
                cufd_data = response.json()
                _logger.info(f"CUFD obtenido desde la API: {cufd_data}")

                # Desactivar el CUFD vigente actual para este Punto de Venta
                cufd_vigente = self.env['l10n_bo_bill.cufd'].search([('id_punto_venta', '=', self.id), ('vigente', '=', True)])
                if cufd_vigente:
                    _logger.info(f"Desactivando CUFD anterior {cufd_vigente.codigo}")
                    cufd_vigente.write({'vigente': False})

                # Convertir las fechas de la API al formato adecuado
                fecha_inicio = datetime.strptime(cufd_data['fechaCreacion'].split('.')[0], '%Y-%m-%dT%H:%M:%S')
                fecha_vigencia = datetime.strptime(cufd_data['fechaVigencia'].split('.')[0], '%Y-%m-%dT%H:%M:%S')

                # Crear el nuevo CUFD en Odoo
                self.env['l10n_bo_bill.cufd'].create({
                    'codigo': cufd_data['codigo'],
                    'codigo_control': cufd_data['codigoControl'],
                    'fecha_inicio': fecha_inicio,
                    'fecha_vigencia': fecha_vigencia,
                    'vigente': cufd_data['estado'],
                    'id_punto_venta': self.id,
                    'external_id': cufd_data['idPuntoVenta'],
                })
            else:
                _logger.error(f"Error al obtener el CUFD desde la API: {response.status_code} {response.text}")
                raise UserError(f"Error al obtener el CUFD desde la API. Código: {response.status_code}, Detalles: {response.text}")

        except requests.exceptions.RequestException as e:
            _logger.error(f"Excepción al obtener el CUFD desde la API: {e}")
            raise UserError(f"Error de conexión con la API: {e}")