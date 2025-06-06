from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class RegistrarEventoContingenciaWizard(models.TransientModel):
    _name = 'registrar.evento.contingencia.wizard'
    _description = 'Wizard para registrar el inicio de un evento de contingencia'

    punto_venta_id = fields.Many2one('l10n_bo_bill.punto_venta', string="Punto de Venta", required=True)
    sucursal_id = fields.Many2one('l10n_bo_bill.sucursal', string="Sucursal", required=True)
    evento_significativo_id = fields.Many2one('l10n_bo_bill.evento_significativo', string="Evento Significativo", required=True)
    descripcion = fields.Char(string="Descripción", required=True)
    fecha_hora_inicio = fields.Datetime(string="Fecha Hora Inicio")
    fecha_hora_fin = fields.Datetime(string="Fecha Hora Fin")
    mostrar_fechas = fields.Boolean(string="Mostrar Fechas", compute='_compute_mostrar_fechas')

    @api.depends('evento_significativo_id')
    def _compute_mostrar_fechas(self):
        """Mostrar los campos de fecha/hora si el código clasificador es 5, 6 o 7."""
        for record in self:
            record.mostrar_fechas = record.evento_significativo_id.codigo_clasificador in ('5', '6', '7')

    @api.model
    def default_get(self, fields):
        res = super(RegistrarEventoContingenciaWizard, self).default_get(fields)
        
        # Buscar el punto de venta principal
        punto_venta_principal = self.env['l10n_bo_bill.punto_venta'].search([('punto_venta_principal', '=', True)], limit=1)
        if not punto_venta_principal:
            raise UserError(_("No se encontró un Punto de Venta principal configurado."))
        
        # Asignar el punto de venta y la sucursal relacionada
        res['punto_venta_id'] = punto_venta_principal.id
        res['sucursal_id'] = punto_venta_principal.id_sucursal.id
        
        return res

    def _get_api_url(self):
        """Función para obtener la URL de la API activa"""
        direccion_apis = self.env['l10n_bo_bill.direccion_api'].search([('activo', '=', True)])
        
        if not direccion_apis:
            raise UserError("No se encontró una configuración de la API activa.")
        
        if len(direccion_apis) > 1:
            raise UserError("Hay más de una dirección de API activa. Verifica la configuración.")

        return direccion_apis[0].url  # Retorna la URL activa

    def action_confirmar_registro_evento(self):
        """Método para enviar los datos a la API de contingencia y guardar el idEvento en el punto de venta."""
        
        # Preparar los datos básicos
        data = {
            "idPuntoVenta": int(self.punto_venta_id.external_id),
            "idSucursal": int(self.sucursal_id.external_id),
            "codigoEvento": int(self.evento_significativo_id.codigo_clasificador),
            "descripcion": self.descripcion
        }

        # Verificar el endpoint y los datos adicionales en función del codigo_clasificador
        if self.mostrar_fechas:  # Esto indica que el codigo_clasificador es 5, 6 o 7
            # Agregar fechas
            data["fechaHoraInicio"] = self.fecha_hora_inicio.strftime("%Y-%m-%d %H:%M:%S")
            data["fechaHoraFin"] = self.fecha_hora_fin.strftime("%Y-%m-%d %H:%M:%S")
            # Usar el endpoint de registrar inicio-fin-evento
            api_url = f"{self._get_api_url()}/contingencia/registrar-inicio-fin-evento"
        else:
            # Usar el endpoint de registrar inicio-evento
            api_url = f"{self._get_api_url()}/contingencia/registrar-inicio-evento"

        try:
            # Enviar los datos a la API
            response = requests.post(api_url, json=data)
            response.raise_for_status()  # Verificar si hubo un error en la solicitud

            # Manejar la respuesta de la API
            if response.status_code == 200:
                respuesta_json = response.json()
                id_evento = respuesta_json.get("idEvento")
                if id_evento:
                    # Guardar el idEvento en el campo `id_evento` del punto de venta
                    self.punto_venta_id.write({'id_evento': str(id_evento)})
                    _logger.info("Evento registrado correctamente con idEvento: %s", id_evento)
                    _logger.info("Respuesta exitosa de la API: %s", respuesta_json)
                    
                    punto_venta_principal = self.env['l10n_bo_bill.punto_venta'].search([('punto_venta_principal', '=', True)], limit=1)
                    if punto_venta_principal:
                        punto_venta_principal.activar_contingencia()
                else:
                    raise UserError(_("La API no devolvió un idEvento. Respuesta de la API: %s" % respuesta_json))
            else:
                _logger.error("Error en la respuesta de la API: %s", response.text)
                raise UserError(_("Error al registrar el evento. Respuesta de la API: %s" % response.text))

        except requests.exceptions.RequestException as e:
            # Log del error con la respuesta de la API
            _logger.error("Error al conectar con la API: %s", e)
            raise UserError(_("Error al conectar con la API: %s" % e))
