import React from "react";

const NotFoundPage: React.FC = () => (
  <h1
    style={{
      position: "absolute",
      top: "50%",
      left: "50%",
      transform: "translateX(-50%) translateY(-50%)",
    }}
  >
    Sorry, we couldn't find that page. Go <a href="/">home</a>.
  </h1>
);

export default NotFoundPage;
