from PyQt4 import QtCore, QtGui

import math


eleColor={'E_GUN':'purple', 'SBEND':'red', 'QUADRUPOLE':'blue', 'DRIFT':'black', 'LCAVITY':'green', 'RFCAVITY':'green', 'SEXTUPOLE':'yellow', 'WIGGLER':'orange'}
eleWidth={'E_GUN':1.0, 'LCAVITY':0.4, 'RFCAVITY':0.4, 'SBEND':0.6, 'QUADRUPOLE':0.4, 'SEXTUPOLE':0.5, 'DRIFT':0.1}

def EleWidth(ele, default=0.2):
    if ele.key in eleWidth:
        return eleWidth[ele.key]
    else:
        return default

def EleColor(ele, default='black'):
    if ele.key in eleColor:
        return QtGui.QColor(eleColor[ele.key])
    else:
        return QtGui.QColor(default)


class EleGraphicsItem(QtGui.QGraphicsItem):
    def __init__(self, ele, scale=1, units='m', parent = None):
        super(EleGraphicsItem, self).__init__(parent)
        self.setAcceptHoverEvents(True)
        self.name = ele.name
        self.ele = ele
        self.units = units
        self._sc = scale
        self._r1 = self._sc*0.5*EleWidth(self.ele) # Inner wall width
        self._r2 = self._sc*0.5*EleWidth(self.ele) # Outer wall width
        self._angle = self.ele.value['angle']
        self._length = self._sc*self.ele.value['L']
        self._width = self._r1+self._r2
        self._shape = self._EleShape()

    def _EleShape(self):
        """ returns a QPainterPath that outlines the ele """
        path = QtGui.QPainterPath()
        angle = self._angle
        length = self._length
        r1 = self._r1
        r2 = self._r2
        if angle != 0:
            # Curved Geometry
            rho = length/angle
            st = math.sin(angle)
            ct = math.cos(angle)
            path.moveTo(0, 0)
            path.lineTo(0, r1)
            path.arcTo(-rho+r1, r1, 2*(rho-r1), 2*(rho-r1), 90.0, angle*180.0/math.pi)
            path.lineTo(-(rho+r2)*st, rho-ct*(rho+r2))
            path.arcTo(-rho-r2,-r2, 2*(rho+r2), 2*(rho+r2), 90.0+angle*180.0/math.pi, -angle*180.0/math.pi)
            path.lineTo(0, 0)
            if angle > 0:
                w = (r2+rho)*st
                h = r2 + rho*(1-ct) + r1*ct
                self._boundingRect = QtCore.QRectF(-1.05*w,-1.05*r2, 1.1*w, 1.1*h)
            else:
                w = (rho-r1)*st
                h = r1 + r2*ct - rho*(1-ct)
                self._boundingRect = QtCore.QRectF(-1.05*w, 1.05*(-h+r1), 1.1*w, 1.1*h)

        else:
            # Straight Geometry
            w = self._length
            h = self._width
            self._boundingRect = QtCore.QRectF(-1.05*w, -1.1*r2, 1.1*w, 1.1*h)
            path.moveTo(0, 0)
            path.lineTo(0, -r2)
            path.lineTo(-w, -r2)
            path.lineTo(-w,  r1)
            path.lineTo(0, r1)
            path.lineTo(0, 0)
        return path

    def boundingRect(self):
        return  self._boundingRect

    def hoverEnterEvent(self, event):
        self.__printGeometryDetails()

    def paint(self, painter, option, widget):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Draw and fill shape
        painter.drawPath(self._shape)
        painter.fillPath(self._shape,  EleColor(self.ele))

        # Reference Orbit for curved and straight geometries
        painter.setPen(QtCore.Qt.DashLine)
        if self._angle != 0:
            rho = self._length/self._angle
            path2 = QtGui.QPainterPath()
            path2.arcTo(-rho, 0, 2*rho, 2*rho, 90, self._angle*180/math.pi)
            painter.drawPath(path2)

        else:
            line = QtCore.QLineF(-self._length, 0, 0, 0)
            painter.drawLine(line)

        # isSelected highlighting
        if self.isSelected():
            painter.drawRect(self.boundingRect())

    def shape(self):
        return self._shape


class LatticeView(QtGui.QGraphicsView):

    def __init__(self, lattice, parent = None):
        super(LatticeView, self).__init__(parent)

        self._sc = 100
        self.units = 'cm'
        self.setInteractive(True)
        self.setGeometry(QtCore.QRect(200, 200, 400, 400))

        self.scene = QtGui.QGraphicsScene(self)
        self.setScene(self.scene)
        self.pt_to_meter = 1.0
        self.setDragMode(QtGui.QGraphicsView.ScrollHandDrag)

        # Gather a list of x and y coordinates
        xlist = []
        ylist = []
        for ele in lattice.ele:
            item = EleGraphicsItem(ele, self._sc, self.units )
            item.setFlag(QtGui.QGraphicsItem.ItemIsSelectable, True)
            item.setFlag(QtGui.QGraphicsItem.ItemIsMovable, True)
            xlist.append(self._sc*ele.floor.z)
            ylist.append(-self._sc*ele.floor.x)
            item.setPos( self._sc*ele.floor.z, -self._sc*ele.floor.x)
            item.setRotation(-ele.floor.theta*180/math.pi)
            self.scene.addItem(item)
        xmin = min(xlist)
        xmax = max(xlist)
        ymin = min(ylist)
        ymax = max(ylist)
        xsize = (xmax-xmin)
        ysize = (ymax-ymin)
        scale = max(xsize, ysize)/200
        self.zoom(1/scale)
        self.scene.setSceneRect(QtCore.QRectF(1.05*scale*xmin, 1.05*scale*ymin, 1.1*scale*xsize, 1.1*scale*ysize))

        self.scene.selectionChanged.connect(self.printSelectedItems)

    def ix_ele_SelectedItems(self):
        return [x.ele.ix_ele for x in self.scene.selectedItems()]

    def printSelectedItems(self):
        items = self.scene.selectedItems()
        names = [x.name for x in items]

    def zoom(self, scale):
        """ function to uniformly zoom, and keep track of the screen's scale"""
        self.pt_to_meter = self.pt_to_meter*scale
        self.scale(scale,scale)
        print('scale ', 1/self.pt_to_meter, ' m/pt')

    def wheelEvent(self, event):
        sc =  1.0 + event.delta()/1000.0
        self.zoom(sc)
