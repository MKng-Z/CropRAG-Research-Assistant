package com.playground.croprag;

import java.util.concurrent.CountDownLatch;

import org.neo4j.configuration.GraphDatabaseSettings;
import org.neo4j.configuration.connectors.BoltConnector;
import org.neo4j.configuration.connectors.HttpConnector;
import org.neo4j.configuration.connectors.HttpsConnector;
import org.neo4j.configuration.helpers.SocketAddress;
import org.neo4j.harness.Neo4j;
import org.neo4j.harness.Neo4jBuilders;

public final class Neo4jHarnessRunner {
    private Neo4jHarnessRunner() {
    }

    public static void main(String[] args) throws Exception {
        Neo4j neo4j = Neo4jBuilders.newInProcessBuilder()
            .withConfig(GraphDatabaseSettings.auth_enabled, false)
            .withConfig(GraphDatabaseSettings.strict_config_validation, false)
            .withConfig(BoltConnector.enabled, true)
            .withConfig(HttpConnector.enabled, true)
            .withConfig(HttpsConnector.enabled, false)
            .withConfig(BoltConnector.listen_address, new SocketAddress("localhost", 7687))
            .withConfig(HttpConnector.listen_address, new SocketAddress("localhost", 7474))
            .build();

        Runtime.getRuntime().addShutdownHook(new Thread(neo4j::close));

        System.out.println("NEO4J_HARNESS_STARTED");
        System.out.println("bolt=" + neo4j.boltURI());
        System.out.println("http=" + neo4j.httpURI());
        new CountDownLatch(1).await();
    }
}