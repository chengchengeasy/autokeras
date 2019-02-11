from abc import abstractmethod

from autokeras.constant import Constant
from autokeras.nn.graph import Graph
from autokeras.nn.layers import StubAdd, StubDense, StubReLU, get_conv_class, get_dropout_class, \
    get_global_avg_pooling_class, get_pooling_class, get_avg_pooling_class, get_batch_norm_class, StubDropout1d, \
    StubConcatenate


class NetworkGenerator:
    """The base class for generating a network.

    It can be used to generate a CNN or Multi-Layer Perceptron.

    Attributes:
        n_output_node: Number of output nodes in the network.
        input_shape: A tuple to represent the input shape.
    """

    def __init__(self, n_output_node, input_shape):
        """Initialize the instance.

        Sets the parameters `n_output_node` and `input_shape` for the instance.

        Args:
            n_output_node: An integer. Number of output nodes in the network.
            input_shape: A tuple. Input shape of the network.
        """
        self.n_output_node = n_output_node
        self.input_shape = input_shape

    @abstractmethod
    def generate(self, model_len, model_width):
        pass


class CnnGenerator(NetworkGenerator):
    """A class to generate CNN.

    Attributes:
          n_dim: `len(self.input_shape) - 1`
          conv: A class that represents `(n_dim-1)` dimensional convolution.
          dropout: A class that represents `(n_dim-1)` dimensional dropout.
          global_avg_pooling: A class that represents `(n_dim-1)` dimensional Global Average Pooling.
          pooling: A class that represents `(n_dim-1)` dimensional pooling.
          batch_norm: A class that represents `(n_dim-1)` dimensional batch normalization.
    """

    def __init__(self, n_output_node, input_shape):
        """Initialize the instance.

        Args:
            n_output_node: An integer. Number of output nodes in the network.
            input_shape: A tuple. Input shape of the network.
        """
        super(CnnGenerator, self).__init__(n_output_node, input_shape)
        self.n_dim = len(self.input_shape) - 1
        if len(self.input_shape) > 4:
            raise ValueError('The input dimension is too high.')
        if len(self.input_shape) < 2:
            raise ValueError('The input dimension is too low.')
        self.conv = get_conv_class(self.n_dim)
        self.dropout = get_dropout_class(self.n_dim)
        self.global_avg_pooling = get_global_avg_pooling_class(self.n_dim)
        self.pooling = get_pooling_class(self.n_dim)
        self.batch_norm = get_batch_norm_class(self.n_dim)

    def generate(self, model_len=None, model_width=None):
        """Generates a CNN.

        Args:
            model_len: An integer. Number of convolutional layers.
            model_width: An integer. Number of filters for the convolutional layers.

        Returns:
            An instance of the class Graph. Represents the neural architecture graph of the generated model.
        """
        if model_len is None:
            model_len = Constant.MODEL_LEN
        if model_width is None:
            model_width = Constant.MODEL_WIDTH
        pooling_len = int(model_len / 4)
        graph = Graph(self.input_shape, False)
        temp_input_channel = self.input_shape[-1]
        output_node_id = 0
        stride = 1
        for i in range(model_len):
            output_node_id = graph.add_layer(StubReLU(), output_node_id)
            output_node_id = graph.add_layer(self.batch_norm(graph.node_list[output_node_id].shape[-1]), output_node_id)
            output_node_id = graph.add_layer(self.conv(temp_input_channel,
                                                       model_width,
                                                       kernel_size=3,
                                                       stride=stride), output_node_id)
            # if stride == 1:
            #     stride = 2
            temp_input_channel = model_width
            if pooling_len == 0 or ((i + 1) % pooling_len == 0 and i != model_len - 1):
                output_node_id = graph.add_layer(self.pooling(), output_node_id)

        output_node_id = graph.add_layer(self.global_avg_pooling(), output_node_id)
        output_node_id = graph.add_layer(self.dropout(Constant.CONV_DROPOUT_RATE), output_node_id)
        output_node_id = graph.add_layer(StubDense(graph.node_list[output_node_id].shape[0], model_width),
                                         output_node_id)
        output_node_id = graph.add_layer(StubReLU(), output_node_id)
        graph.add_layer(StubDense(model_width, self.n_output_node), output_node_id)
        return graph


class MlpGenerator(NetworkGenerator):
    """A class to generate Multi-Layer Perceptron.
    """

    def __init__(self, n_output_node, input_shape):
        """Initialize the instance.

        Args:
            n_output_node: An integer. Number of output nodes in the network.
            input_shape: A tuple. Input shape of the network. If it is 1D, ensure the value is appended by a comma
                in the tuple.
        """
        super(MlpGenerator, self).__init__(n_output_node, input_shape)
        if len(self.input_shape) > 1:
            raise ValueError('The input dimension is too high.')

    def generate(self, model_len=None, model_width=None):
        """Generates a Multi-Layer Perceptron.

        Args:
            model_len: An integer. Number of hidden layers.
            model_width: An integer or a list of integers of length `model_len`. If it is a list, it represents the
                number of nodes in each hidden layer. If it is an integer, all hidden layers have nodes equal to this
                value.

        Returns:
            An instance of the class Graph. Represents the neural architecture graph of the generated model.
        """
        if model_len is None:
            model_len = Constant.MODEL_LEN
        if model_width is None:
            model_width = Constant.MODEL_WIDTH
        if isinstance(model_width, list) and not len(model_width) == model_len:
            raise ValueError('The length of \'model_width\' does not match \'model_len\'')
        elif isinstance(model_width, int):
            model_width = [model_width] * model_len

        graph = Graph(self.input_shape, False)
        output_node_id = 0
        n_nodes_prev_layer = self.input_shape[0]
        for width in model_width:
            output_node_id = graph.add_layer(StubDense(n_nodes_prev_layer, width), output_node_id)
            output_node_id = graph.add_layer(StubDropout1d(Constant.MLP_DROPOUT_RATE), output_node_id)
            output_node_id = graph.add_layer(StubReLU(), output_node_id)
            n_nodes_prev_layer = width

        graph.add_layer(StubDense(n_nodes_prev_layer, self.n_output_node), output_node_id)
        return graph


class ResNetGenerator(NetworkGenerator):
    def __init__(self, n_output_node, input_shape, layers=[2, 2, 2, 2], bottleneck=False):
        super(ResNetGenerator, self).__init__(n_output_node, input_shape)
        self.layers = layers
        self.in_planes = 64
        self.n_dim = len(self.input_shape) - 1
        if len(self.input_shape) > 4:
            raise ValueError('The input dimension is too high.')
        elif len(self.input_shape) < 2:
            raise ValueError('The input dimension is too low.')
        self.conv = get_conv_class(self.n_dim)
        self.dropout = get_dropout_class(self.n_dim)
        self.global_avg_pooling = get_global_avg_pooling_class(self.n_dim)
        self.adaptive_avg_pooling = get_global_avg_pooling_class(self.n_dim)
        self.batch_norm = get_batch_norm_class(self.n_dim)
        if bottleneck:
            self.make_block = self._make_bottleneck_block
            self.block_expansion = 1
        else:
            self.make_block = self._make_basic_block
            self.block_expansion = 4

    def generate(self, model_len=None, model_width=None):
        if model_width is None:
            model_width = Constant.MODEL_WIDTH
        graph = Graph(self.input_shape, False)
        temp_input_channel = self.input_shape[-1]
        output_node_id = 0
        output_node_id = graph.add_layer(self.conv(temp_input_channel, model_width, kernel_size=3), output_node_id)
        output_node_id = graph.add_layer(self.batch_norm(model_width), output_node_id)
        output_node_id = graph.add_layer(StubReLU(), output_node_id)
        # output_node_id = graph.add_layer(self.pooling(kernel_size=3, stride=2, padding=1), output_node_id)

        output_node_id = self._make_layer(graph, model_width, self.layers[0], output_node_id, 1)
        model_width *= 2
        output_node_id = self._make_layer(graph, model_width, self.layers[1], output_node_id, 2)
        model_width *= 2
        output_node_id = self._make_layer(graph, model_width, self.layers[2], output_node_id, 2)
        model_width *= 2
        output_node_id = self._make_layer(graph, model_width, self.layers[3], output_node_id, 2)

        output_node_id = graph.add_layer(self.global_avg_pooling(), output_node_id)
        graph.add_layer(StubDense(model_width * self.block_expansion, self.n_output_node), output_node_id)
        return graph

    def _make_layer(self, graph, planes, blocks, node_id, stride):
        strides = [stride] + [1] * (blocks - 1)
        out = node_id
        for current_stride in strides:
            out = self.make_block(graph, self.in_planes, planes, out, current_stride)
            self.in_planes = planes * self.block_expansion
        return out

    def _make_basic_block(self, graph, in_planes, planes, node_id, stride=1):
        out = graph.add_layer(self.conv(in_planes, planes, kernel_size=3, stride=stride), node_id)
        out = graph.add_layer(self.batch_norm(planes), out)
        out = graph.add_layer(StubReLU(), out)
        out = graph.add_layer(self.conv(planes, planes, kernel_size=3), out)
        out = graph.add_layer(self.batch_norm(planes), out)

        residual_node_id = node_id

        if stride != 1 or in_planes != self.block_expansion * planes:
            residual_node_id = graph.add_layer(self.conv(in_planes,
                                                         planes * self.block_expansion,
                                                         kernel_size=1,
                                                         stride=stride), residual_node_id)
            residual_node_id = graph.add_layer(self.batch_norm(self.block_expansion*planes), residual_node_id)

        out = graph.add_layer(StubAdd(), (out, residual_node_id))
        out = graph.add_layer(StubReLU(), out)
        return out

    def _make_bottleneck_block(self, graph, in_planes, planes, node_id, stride=1):
        out = graph.add_layer(self.conv(in_planes, planes, kernel_size=1), node_id)
        out = graph.add_layer(self.batch_norm(planes), out)
        out = graph.add_layer(StubReLU(), out)
        out = graph.add_layer(self.conv(planes, planes, kernel_size=3, stride=stride), out)
        out = graph.add_layer(self.batch_norm(planes), out)
        out = graph.add_layer(StubReLU(), out)
        out = graph.add_layer(self.conv(planes, self.block_expansion*planes, kernel_size=1), out)
        out = graph.add_layer(self.batch_norm(self.block_expansion*planes), out)

        residual_node_id = node_id

        if stride != 1 or in_planes != self.block_expansion*planes:
            residual_node_id = graph.add_layer(self.conv(in_planes,
                                                         planes * self.block_expansion,
                                                         kernel_size=1,
                                                         stride=stride), residual_node_id)
            residual_node_id = graph.add_layer(self.batch_norm(self.block_expansion*planes), residual_node_id)

        out = graph.add_layer(StubAdd(), (out, residual_node_id))
        out = graph.add_layer(StubReLU(), out)
        return out


def ResNet18(n_output_node, input_shape):
    return ResNetGenerator(n_output_node, input_shape)


def ResNet34(n_output_node, input_shape):
    return ResNetGenerator(n_output_node, input_shape, [3, 4, 6, 3])


def ResNet50(n_output_node, input_shape):
    return ResNetGenerator(n_output_node, input_shape, [3, 4, 6, 3], bottleneck=True)


def ResNet101(n_output_node, input_shape):
    return ResNetGenerator(n_output_node, input_shape, [3, 4, 23, 3], bottleneck=True)


def ResNet152(n_output_node, input_shape):
    return ResNetGenerator(n_output_node, input_shape, [3, 8, 36, 3], bottleneck=True)


class DenseNetGenerator(NetworkGenerator):
    def __init__(self, n_output_node, input_shape, block_config=[6, 12, 24, 16], growth_rate=32):
        super().__init__(n_output_node, input_shape)
        # DenseNet Constant
        self.num_init_features = 64
        self.growth_rate = growth_rate
        self.block_config = block_config
        self.bn_size = 4
        self.drop_rate = 0
        # Stub layers
        self.n_dim = len(self.input_shape) - 1
        self.conv = get_conv_class(self.n_dim)
        self.dropout = get_dropout_class(self.n_dim)
        self.global_avg_pooling = get_global_avg_pooling_class(self.n_dim)
        self.adaptive_avg_pooling = get_global_avg_pooling_class(self.n_dim)
        self.max_pooling = get_pooling_class(self.n_dim)
        self.avg_pooling = get_avg_pooling_class(self.n_dim)
        self.batch_norm = get_batch_norm_class(self.n_dim)

    def generate(self, model_len=None, model_width=None):
        if model_len is None:
            model_len = Constant.MODEL_LEN
        if model_width is None:
            model_width = Constant.MODEL_WIDTH
        graph = Graph(self.input_shape, False)
        temp_input_channel = self.input_shape[-1]
        # First convolution
        output_node_id = 0
        output_node_id = graph.add_layer(self.conv(temp_input_channel, model_width, kernel_size=7),
                                         output_node_id)
        output_node_id = graph.add_layer(self.batch_norm(num_features=self.num_init_features), output_node_id)
        output_node_id = graph.add_layer(StubReLU(), output_node_id)
        db_input_node_id = graph.add_layer(self.max_pooling(kernel_size=3, stride=2, padding=1), output_node_id)
        # Each Denseblock
        num_features = self.num_init_features
        for i, num_layers in enumerate(self.block_config):
            db_input_node_id = self._dense_block(num_layers=num_layers, num_input_features=num_features,
                                                 bn_size=self.bn_size, growth_rate=self.growth_rate,
                                                 drop_rate=self.drop_rate,
                                                 graph=graph, input_node_id=db_input_node_id)
            num_features = num_features + num_layers * self.growth_rate
            if i != len(self.block_config) - 1:
                db_input_node_id = self._transition(num_input_features=num_features,
                                                    num_output_features=num_features // 2,
                                                    graph=graph, input_node_id=db_input_node_id)
                num_features = num_features // 2
        # Final batch norm
        out = graph.add_layer(self.batch_norm(num_features), db_input_node_id)

        out = graph.add_layer(StubReLU(), out)
        out = graph.add_layer(self.adaptive_avg_pooling(), out)
        # Linear layer
        graph.add_layer(StubDense(num_features, self.n_output_node), out)
        return graph

    def _dense_block(self, num_layers, num_input_features, bn_size, growth_rate, drop_rate, graph, input_node_id):
        block_input_node = input_node_id
        for i in range(num_layers):
            block_input_node = self._dense_layer(num_input_features + i * growth_rate, growth_rate,
                                                 bn_size, drop_rate,
                                                 graph, block_input_node)
        return block_input_node

    def _dense_layer(self, num_input_features, growth_rate, bn_size, drop_rate, graph, input_node_id):
        out = graph.add_layer(self.batch_norm(num_features=num_input_features), input_node_id)
        out = graph.add_layer(StubReLU(), out)
        out = graph.add_layer(self.conv(num_input_features, bn_size * growth_rate, kernel_size=1, stride=1), out)
        out = graph.add_layer(self.batch_norm(bn_size * growth_rate), out)
        out = graph.add_layer(StubReLU(), out)
        out = graph.add_layer(self.conv(bn_size * growth_rate, growth_rate, kernel_size=3, stride=1, padding=1), out)
        out = graph.add_layer(self.dropout(rate=drop_rate), out)
        out = graph.add_layer(StubConcatenate(), (input_node_id, out))
        return out

    def _transition(self, num_input_features, num_output_features, graph, input_node_id):
        out = graph.add_layer(self.batch_norm(num_features=num_input_features), input_node_id)
        out = graph.add_layer(StubReLU(), out)
        out = graph.add_layer(self.conv(num_input_features, num_output_features, kernel_size=1, stride=1), out)
        out = graph.add_layer(self.avg_pooling(kernel_size=2, stride=2), out)
        return out


def DenseNet121(n_output_node, input_shape):
    return DenseNetGenerator(n_output_node, input_shape)


def DenseNet169(n_output_node, input_shape):
    return DenseNetGenerator(n_output_node, input_shape, [6, 12, 32, 32])


def DenseNet201(n_output_node, input_shape):
    return DenseNetGenerator(n_output_node, input_shape, [6, 12, 48, 32])


def DenseNet161(n_output_node, input_shape):
    return DenseNetGenerator(n_output_node, input_shape, [6, 12, 36, 24], growth_rate=48)

