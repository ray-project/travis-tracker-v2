import { graphql, PageProps } from "gatsby";
import React from "react";

import LayoutWrapper from "../components/layout";
import BuildTimeFooter from "../components/time";
import Title from "../components/title";
import TestCase from "../components/case";

import { SiteFailedTest } from "../interface";
import rawData from "../data.json";
const failedTests = rawData as [SiteFailedTest];

export const query = graphql`
  {
    site {
      buildTime
    }
  }
`;

type DataProps = {
  site: {
    buildTime: string;
  };
};

const App: React.FC<PageProps<DataProps>> = ({ data }) => (
  <LayoutWrapper>
    <Title></Title>

    {failedTests.map((c) => (
      <TestCase case={c}></TestCase>
    ))}

    <BuildTimeFooter
      buildTime={Date.parse(data.site.buildTime)}
    ></BuildTimeFooter>
  </LayoutWrapper>
);

export default App;
