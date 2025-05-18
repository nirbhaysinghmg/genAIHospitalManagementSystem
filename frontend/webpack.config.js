// webpack.config.js
const path = require("path");

module.exports = {
  mode: "production",
  entry: "./src/chatbot-widget.js",
  output: {
    filename: "chatbot-widget.js",
    path: path.resolve(__dirname, "dist"),

    // expose your default export as window.ChatBotWidget
    library: "ChatBotWidget",
    libraryTarget: "umd",
    globalObject: "this",

    // <<< add this line >>>
    libraryExport: "default",
  },
  module: {
    rules: [
      {
        test: /\.jsx?$/,
        exclude: /node_modules/,
        loader: "babel-loader",
        options: { presets: ["@babel/preset-env", "@babel/preset-react"] },
      },
      {
        test: /\.css$/,
        use: ["style-loader", "css-loader"],
      },
    ],
  },
  resolve: { extensions: [".js", ".jsx"] },
};
